"""问卷包装模块的基础测试。"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

import requests

from backend.models import SurveyQuestion, WrappedQuestion, WrappedSurvey
from backend.services import llm_service as llm_module
from backend.services.analytics_service import (
    build_research_analysis,
    build_response,
    build_research_facts,
    calculate_result_type,
    calculate_dimension_scores,
    summarize_responses,
    validate_answers,
)
from backend.storage.database import ResearchDatabase
from backend.services.survey_service import (
    MIN_GENERATED_QUESTIONS,
    _normalize_wrapped_survey,
    _validate_wenjuan_url,
    _validate_wjx_url,
    build_wrapped_survey,
    parse_survey_text,
    parse_wjx_html,
    wrapped_survey_from_dict,
)
from backend.utils.excel_export import build_research_xlsx
from backend.utils.pdf_export import build_research_pdf


class FakeLLMService:
    """测试用假模型，正式运行不会使用。"""

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "survey_name": "恋爱象限测评",
            "theme": "恋爱象限",
            "tagline": "测测你的隐藏消费人格",
            "intro": "凭第一感觉选择即可。",
            "disclosure": "本测评仅供娱乐，部分题目用于市场研究。",
            "result_types": [
                {"name": "理性探索型", "description": "你会认真比较后再决定。"}
            ],
            "questions": [
                {
                    "question_id": "q1",
                    "public_text": "你会为一份心意选择哪个价位？",
                    "question_type": "single_choice",
                    "options": ["100", "200"],
                    "research_tag": "price",
                }
            ],
        }


class FakeAnalysisLLMService:
    """返回固定分析文案，验证数字仍由本地事实决定。"""

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "key_findings": ["样本在该主题维度上呈现可观察差异。"],
            "dimension_conclusions": [
                {"key": "initiative", "conclusion": "该维度反映样本的行动倾向。"}
            ],
            "research_conclusion": "当前样本可以支持初步研究判断。",
            "long_summary": "这是一段用于测试的完整总结文字。",
            "limitations": "测试样本不代表总体人群。",
        }


def test_parse_csv_questionnaire() -> None:
    content = "id,question,type,options,research_tag\nq1,愿意支付多少,single_choice,100|200|300,price\n"
    questions = parse_survey_text(content, "survey.csv")
    assert len(questions) == 1
    assert questions[0].options == ["100", "200", "300"]


def test_parse_wjx_html_questionnaire() -> None:
    content = """
    <html>
      <head><title>大学生消费调查</title></head>
      <body>
        <div id="divQuestion">
          <div class="field ui-field-contain" topic="1" id="div1" req="1" type="3">
            <div class="field-label"><span>*</span><div class="topicnumber">1.</div><div class="topichtml">你的性别</div></div>
            <div class="ui-radio"><input type="radio" name="q1"><div class="label" dit="%e7%94%b7">男</div></div>
            <div class="ui-radio"><input type="radio" name="q1"><div class="label" dit="%e5%a5%b3">女</div></div>
          </div>
          <div class="field ui-field-contain" topic="2" id="div2" req="0" type="4">
            <div class="field-label"><div class="topicnumber">2.</div><div class="topichtml">每月消费多用在哪些方面</div></div>
            <div class="ui-checkbox"><input type="checkbox" name="q2"><div class="label">伙食</div></div>
            <div class="ui-checkbox"><input type="checkbox" name="q2"><div class="label">交通</div></div>
          </div>
          <div class="field ui-field-contain" topic="3" id="div3" req="1" type="1">
            <div class="field-label"><div class="topicnumber">3.</div><div class="topichtml">请填写学校名称</div></div>
            <input type="text" name="q3">
          </div>
        </div>
      </body>
    </html>
    """
    title, questions = parse_wjx_html(content, "https://v.wjx.cn/vm/example.aspx")
    assert title == "大学生消费调查"
    assert [question.question_id for question in questions] == ["q1", "q2", "q3"]
    assert questions[0].options == ["男", "女"]
    assert questions[1].question_type == "multiple_choice"
    assert questions[1].required is False
    assert questions[2].question_type == "text"


def test_parse_wjx_rejects_non_wjx_url() -> None:
    try:
        _validate_wjx_url("https://example.com/survey")
    except ValueError as exc:
        assert "问卷星域名" in str(exc)
    else:
        raise AssertionError("非问卷星链接应被拒绝")


def test_import_links_accept_common_bare_domains() -> None:
    assert _validate_wjx_url("v.wjx.cn/vm/example.aspx") == "https://v.wjx.cn/vm/example.aspx"
    assert (
        _validate_wenjuan_url("www.wenjuan.com/lib_detail_full/example/")
        == "https://www.wenjuan.com/lib_detail_full/example/"
    )


def test_parse_wjx_unavailable_page_has_clear_error() -> None:
    content = """
    <html>
      <body>
        <div id="divWorkError">
          <h2>提示信息</h2>
          <p id="divInfo">问卷已停止填写</p>
        </div>
      </body>
    </html>
    """
    try:
        parse_wjx_html(content, "https://v.wjx.cn/wjx/checkstatus.aspx")
    except ValueError as exc:
        assert "不可访问" in str(exc)
    else:
        raise AssertionError("问卷星不可用页面应给出明确提示")


def test_wrap_preserves_research_mapping() -> None:
    questions = [
        SurveyQuestion(
            "q1", "你愿意支付多少", options=["100", "200"], research_tag="price"
        )
    ]
    survey = build_wrapped_survey(
        questions, "测试价格定位", "恋爱象限", llm_service=FakeLLMService()
    )
    response = build_response(survey, {"q1": "200"}, "理性探索型")
    summary = summarize_responses(survey, [response])
    assert response.research_answers["price"] == "200"
    assert summary["response_count"] == 1


def test_wrap_title_summarizes_packaged_survey() -> None:
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "价格", options=["100", "200"])],
        "测试",
        "周末旅行决策风格",
        llm_service=FakeLLMService(),
    )
    assert survey.theme == "周末旅行决策风格"
    assert survey.survey_name == "周末旅行里的选择剧本"
    assert survey.survey_name != "周末旅行决策风格测评"


def test_finished_survey_title_is_kept_when_not_simple_theme_suffix() -> None:
    raw = {
        "survey_name": "周末旅行里的选择剧本",
        "title_source": "finished_survey",
        "theme": "周末旅行决策风格",
        "dimensions": [
            {"key": "planning", "name": "计划感"},
            {"key": "spontaneity", "name": "即兴度"},
        ],
        "result_types": [
            {"name": "规划型", "description": "提前安排。"},
            {"name": "随兴型", "description": "看心情行动。"},
            {"name": "平衡型", "description": "兼顾效率和惊喜。"},
            {"name": "探索型", "description": "喜欢新鲜路线。"},
        ],
        "questions": [
            {
                "question_id": f"iq{index}",
                "public_text": f"周末出行场景 {index}",
                "question_type": "single_choice",
                "options": ["先看攻略", "到现场再说"],
                "option_scores": {
                    "先看攻略": {"planning": 0.6, "spontaneity": -0.3},
                    "到现场再说": {"planning": -0.4, "spontaneity": 0.7},
                },
                "dimension_weights": {"planning": 1.0, "spontaneity": 1.0},
            }
            for index in range(1, MIN_GENERATED_QUESTIONS + 1)
        ],
    }

    survey = _normalize_wrapped_survey(raw, [], "测试", "周末旅行决策风格")

    assert survey.survey_name == "周末旅行里的选择剧本"


def test_wrap_keeps_original_options_and_falls_back_for_missing_questions() -> None:
    questions = [
        SurveyQuestion("q1", "价格", options=["100", "200"], research_tag="price"),
        SurveyQuestion("q2", "渠道", options=["线上", "线下"], research_tag="channel"),
    ]
    survey = build_wrapped_survey(
        questions, "测试", "主题", llm_service=FakeLLMService()
    )
    assert [question.question_id for question in survey.questions] == ["q1", "q2"]
    assert survey.questions[0].options == ["100", "200"]
    assert survey.questions[1].public_text == "渠道"


def test_validate_answers_rejects_missing_and_invalid_options() -> None:
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "价格", options=["100", "200"], research_tag="price")],
        "测试",
        "主题",
        llm_service=FakeLLMService(),
    )
    try:
        validate_answers(survey, {})
    except ValueError as exc:
        assert "q1" in str(exc)
    else:
        raise AssertionError("缺少必答题时应抛出异常")

    try:
        validate_answers(survey, {"q1": "999"})
    except ValueError as exc:
        assert "无效选项" in str(exc)
    else:
        raise AssertionError("无效选项时应抛出异常")


def test_result_type_is_determined_by_answers() -> None:
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "价格", options=["100", "200"], research_tag="price")],
        "测试",
        "主题",
        llm_service=FakeLLMService(),
    )
    assert calculate_result_type(survey, {"q1": "200"})["name"] == "理性探索型"


def test_generated_survey_requires_enough_questions() -> None:
    raw = {
        "dimensions": [
            {
                "key": "initiative",
                "name": "主动性",
                "description": "面对机会时的行动倾向",
            }
        ],
        "questions": [
            {
                "question_id": "iq1",
                "public_text": "你会怎么做？",
                "question_type": "single_choice",
                "options": ["先观察", "马上行动"],
                "option_scores": {
                    "先观察": {"initiative": -0.5},
                    "马上行动": {"initiative": 0.5},
                },
            }
        ],
    }

    try:
        _normalize_wrapped_survey(raw, [], "测试", "行动风格")
    except ValueError as exc:
        assert str(MIN_GENERATED_QUESTIONS) in str(exc)
    else:
        raise AssertionError("互动题少于最低数量时应拒绝保存")


def test_generated_result_types_get_distinct_dimension_profiles() -> None:
    raw = {
        "dimensions": [
            {"key": "initiative", "name": "主动性"},
            {"key": "prudence", "name": "谨慎度"},
        ],
        "result_types": [
            {"name": "开拓型", "description": "行动快。"},
            {"name": "协调型", "description": "重平衡。"},
            {"name": "守护型", "description": "更谨慎。"},
            {"name": "观察型", "description": "先看清。"},
        ],
        "questions": [
            {
                "question_id": f"iq{index}",
                "public_text": f"场景 {index}",
                "question_type": "single_choice",
                "options": ["先观察", "马上行动"],
                "option_scores": {
                    "先观察": {"initiative": -0.5, "prudence": 0.5},
                    "马上行动": {"initiative": 0.5, "prudence": -0.5},
                },
                "dimension_weights": {"initiative": 1.0, "prudence": 1.0},
            }
            for index in range(1, MIN_GENERATED_QUESTIONS + 1)
        ],
    }

    survey = _normalize_wrapped_survey(raw, [], "测试", "行动风格")
    profiles = [
        item["dimension_profile"] for item in survey.result_types
    ]

    assert all(set(profile) == {"initiative", "prudence"} for profile in profiles)
    assert len({tuple(profile.items()) for profile in profiles}) == 4


def test_result_type_uses_completed_profiles_instead_of_always_first() -> None:
    questions = [
        WrappedQuestion(
            question_id="iq1",
            public_text="你会怎么做？",
            question_type="single_choice",
            options=["先观察", "马上行动"],
            option_scores={
                "先观察": {"initiative": -0.9, "prudence": 0.9},
                "马上行动": {"initiative": 0.9, "prudence": -0.9},
            },
            dimension_weights={"initiative": 1.0, "prudence": 1.0},
        )
    ]
    survey = WrappedSurvey(
        survey_name="行动风格测评",
        theme="行动风格",
        tagline="",
        intro="",
        disclosure="",
        dimensions=[
            {"key": "initiative", "name": "主动性"},
            {"key": "prudence", "name": "谨慎度"},
        ],
        result_types=[
            {
                "name": "守护型",
                "description": "",
                "dimension_profile": {"initiative": -0.9, "prudence": 0.9},
            },
            {
                "name": "开拓型",
                "description": "",
                "dimension_profile": {"initiative": 0.9, "prudence": -0.9},
            },
        ],
        questions=questions,
    )

    result = calculate_result_type(survey, {"iq1": "马上行动"})

    assert result["name"] == "开拓型"


def test_saved_survey_restore_completes_result_profiles() -> None:
    payload = {
        "survey_name": "行动风格测评",
        "theme": "行动风格",
        "tagline": "",
        "intro": "",
        "disclosure": "",
        "dimensions": [
            {"key": "initiative", "name": "主动性"},
            {"key": "prudence", "name": "谨慎度"},
        ],
        "result_types": [
            {"name": "开拓型"},
            {"name": "协调型"},
            {"name": "守护型"},
            {"name": "观察型"},
        ],
        "questions": [
            {
                "question_id": "iq1",
                "public_text": "你会怎么做？",
                "question_type": "single_choice",
                "options": ["先观察", "马上行动"],
                "option_scores": {
                    "先观察": {"initiative": -0.8, "prudence": 0.8},
                    "马上行动": {"initiative": 0.8, "prudence": -0.8},
                },
                "dimension_weights": {"initiative": 1.0, "prudence": 1.0},
            }
        ],
    }

    survey = wrapped_survey_from_dict(payload)

    assert all(
        set(item["dimension_profile"]) == {"initiative", "prudence"}
        for item in survey.result_types
    )


def test_dimension_scores_ignore_unconfigured_questions() -> None:
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "价格", options=["100", "200"])],
        "测试",
        "主题",
        llm_service=FakeLLMService(),
    )
    survey.dimensions = [
        {"key": "initiative", "name": "主动性"},
        {"key": "prudence", "name": "谨慎度"},
    ]
    survey.questions[0].option_scores = {"200": {"initiative": 1.0}}
    survey.questions[0].dimension_weights = {"initiative": 1.0, "prudence": 1.0}

    scores = calculate_dimension_scores(survey, {"q1": "200"})

    assert scores == {"initiative": 1.0, "prudence": 0.0}


def test_research_facts_keep_exact_counts_and_percentages() -> None:
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "你会怎么做", options=["先观察", "马上行动"], research_tag="行动")],
        "大学生消费情况调查",
        "行动风格",
        llm_service=FakeLLMService(),
    )
    survey.dimensions = [
        {
            "key": "initiative",
            "name": "主动性",
            "description": "面对机会时的行动倾向",
            "high_pole": "更主动",
            "low_pole": "更谨慎",
        }
    ]
    survey.questions[0].option_scores = {
        "先观察": {"initiative": -0.5},
        "马上行动": {"initiative": 0.5},
    }
    survey.questions[0].dimension_weights = {"initiative": 1.0}
    responses = [
        build_response(survey, {"q1": "先观察"}, "探索型"),
        build_response(survey, {"q1": "马上行动"}, "探索型"),
    ]

    facts = build_research_facts(survey, responses)

    assert facts["response_count"] == 2
    assert facts["result_types"] == [
        {
            "name": "理性探索型",
            "description": "你会认真比较后再决定。",
            "dimension_profile": {},
            "strengths": [],
            "watchouts": [],
            "advice": "",
            "count": 0,
            "percentage": 0.0,
        },
        {
            "name": "探索型",
            "description": "",
            "dimension_profile": {},
            "strengths": [],
            "watchouts": [],
            "advice": "",
            "count": 2,
            "percentage": 100.0,
        },
    ]
    assert facts["questions"][0]["options"] == [
        {"option": "先观察", "count": 1, "percentage": 50.0},
        {"option": "马上行动", "count": 1, "percentage": 50.0},
    ]
    assert facts["dimensions"][0]["index"] == 50.0


def test_ai_research_analysis_preserves_local_facts() -> None:
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "你会怎么做", options=["先观察", "马上行动"], research_tag="行动")],
        "大学生消费情况调查",
        "行动风格",
        llm_service=FakeLLMService(),
    )
    survey.dimensions = [{"key": "initiative", "name": "主动性"}]
    survey.questions[0].option_scores = {
        "先观察": {"initiative": -0.5},
        "马上行动": {"initiative": 0.5},
    }
    survey.questions[0].dimension_weights = {"initiative": 1.0}
    responses = [
        build_response(survey, {"q1": "马上行动"}, "探索型"),
        build_response(survey, {"q1": "马上行动"}, "探索型"),
    ]

    analysis = build_research_analysis(survey, responses, FakeAnalysisLLMService())

    assert analysis["response_count"] == 2
    assert analysis["questions"][0]["options"][1]["count"] == 2
    assert analysis["questions"][0]["options"][1]["percentage"] == 100.0
    assert analysis["research_conclusion"] == "当前样本可以支持初步研究判断。"


def test_excel_export_includes_mapping_scores_and_response_analysis() -> None:
    survey = WrappedSurvey(
        survey_name="行动风格测评",
        theme="行动风格",
        tagline="",
        intro="",
        disclosure="",
        brand_goal="研究行动倾向",
        dimensions=[{"key": "initiative", "name": "主动性"}],
        result_types=[],
        questions=[
            WrappedQuestion(
                question_id="q1",
                public_text="你会怎么做？",
                question_type="single_choice",
                options=["先观察", "马上行动"],
                research_tag="行动",
                source_text="面对机会你会怎么做？",
                research_refs=["原题 1"],
                option_scores={"马上行动": {"initiative": 0.8}},
                dimension_weights={"initiative": 1.0},
                rationale="映射行动倾向。",
            )
        ],
    )
    response_rows = [
        {
            "id": 1,
            "created_at": "2026-09-17T10:00:00",
            "result_type": "开拓型",
            "answers": {"q1": "马上行动"},
            "research_answers": {"行动": "马上行动"},
            "dimension_scores": {"initiative": 0.8},
            "analysis": {
                "summary": "积极解析",
                "strengths": ["行动快"],
                "watchouts": ["留意风险"],
                "advice": "先验证再推进。",
                "evidence": [
                    {
                        "question": "你会怎么做？",
                        "answer": "马上行动",
                        "reason": "主动性更高。",
                    }
                ],
            },
        }
    ]
    summary = {
        "response_count": 1,
        "research_tags": ["行动"],
        "dimension_stats": [
            {
                "key": "initiative",
                "name": "主动性",
                "score": 0.8,
                "index": 90,
                "coverage_count": 1,
                "positive_count": 1,
                "neutral_count": 0,
                "negative_count": 0,
                "mapped_research_tags": ["行动"],
                "mapped_question_ids": ["q1"],
            }
        ],
    }

    content = build_research_xlsx(survey, response_rows, summary, None)
    with ZipFile(BytesIO(content)) as archive:
        workbook_text = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("xl/worksheets/")
        )

    assert "选项评分映射" in workbook_text
    assert "马上行动 -&gt; initiative:0.8" in workbook_text
    assert "维度分数：主动性" in workbook_text
    assert "结果解析" in workbook_text
    assert "积极解析" in workbook_text
    assert "你会怎么做？｜马上行动｜主动性更高。" in workbook_text


def test_pdf_export_builds_result_and_dimension_detail_tables() -> None:
    survey = WrappedSurvey(
        survey_name="行动风格测评",
        theme="行动风格",
        tagline="",
        intro="",
        disclosure="",
        brand_goal="研究行动倾向",
        dimensions=[{"key": "initiative", "name": "主动性"}],
        result_types=[],
        questions=[],
    )
    summary = {
        "response_count": 2,
        "analysis": {
            "research_goal": "研究行动倾向",
            "theme": "行动风格",
            "result_types": [
                {
                    "name": "开拓型",
                    "count": 1,
                    "percentage": 50.0,
                    "personality_reference": "果断的行动者",
                    "description": "行动更快。",
                    "dimension_profile": {"initiative": 0.9},
                    "strengths": ["推进快"],
                    "watchouts": ["留意节奏"],
                    "advice": "保留复盘。",
                }
            ],
            "dimensions": [
                {
                    "key": "initiative",
                    "name": "主动性",
                    "description": "面对机会时的行动倾向",
                    "high_pole": "更主动",
                    "low_pole": "更谨慎",
                    "index": 90,
                    "score": 0.8,
                    "coverage_count": 2,
                    "positive_count": 1,
                    "neutral_count": 1,
                    "negative_count": 0,
                    "mapped_research_tags": ["行动"],
                    "mapped_question_ids": ["q1"],
                    "conclusion": "样本主动性较高。",
                }
            ],
            "questions": [],
        },
    }
    captured_rows = []

    class FakeDocument:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def build(self, story) -> None:
            return None

    class FakeTable:
        def __init__(self, rows, *args, **kwargs) -> None:
            captured_rows.extend(str(cell.text) for row in rows for cell in row)

        def setStyle(self, style) -> None:
            return None

    with (
        patch("backend.utils.pdf_export.SimpleDocTemplate", FakeDocument),
        patch("backend.utils.pdf_export.Table", FakeTable),
    ):
        build_research_pdf(survey, summary)

    table_text = "\n".join(captured_rows)
    assert "人格参考" in table_text
    assert "果断的行动者" in table_text
    assert "维度画像" in table_text
    assert "initiative:0.9" in table_text
    assert "高分：更主动" in table_text
    assert "正向：1" in table_text
    assert "标签：行动" in table_text


def test_database_survey_status_changes_to_ended(tmp_path) -> None:
    database = ResearchDatabase(str(tmp_path / "survey.sqlite"))
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "价格", options=["100", "200"])],
        "大学生消费情况调查",
        "消费偏好",
        llm_service=FakeLLMService(),
    )
    survey_id = database.save_survey(survey)

    assert database.get_survey(survey_id)["status"] == "open"
    database.finish_survey(survey_id, {"research_conclusion": "完成"})

    saved = database.get_survey(survey_id)
    assert saved["status"] == "ended"
    assert saved["analysis"]["research_conclusion"] == "完成"
    assert database.list_surveys(status="open") == []
    assert database.list_surveys(status="ended")[0]["id"] == survey_id


def test_database_trash_restore_and_permanent_delete(tmp_path) -> None:
    database = ResearchDatabase(str(tmp_path / "survey.sqlite"))
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "价格", options=["100", "200"], research_tag="价格")],
        "大学生消费情况调查",
        "消费偏好",
        llm_service=FakeLLMService(),
    )
    survey_id = database.save_survey(survey)
    database.save_response(build_response(survey, {"q1": "100"}, "探索型"), survey_id)

    trashed = database.move_survey_to_trash(survey_id)

    assert trashed["deleted_at"]
    assert database.list_surveys(status="open") == []
    assert database.list_surveys(deleted=True)[0]["id"] == survey_id

    restored = database.restore_survey(survey_id)

    assert restored["deleted_at"] is None
    assert database.list_surveys(status="open")[0]["id"] == survey_id
    assert database.permanently_delete_survey(survey_id) is False

    database.move_survey_to_trash(survey_id)

    assert database.permanently_delete_survey(survey_id) is True
    assert database.get_survey(survey_id) is None
    assert database.list_responses(survey_id) == []


def test_llm_service_falls_back_to_tokenrhythm(monkeypatch) -> None:
    """主 gpt-5.5 接口失败时应切到基元律动 Chat Completions。"""

    fake_settings = SimpleNamespace(
        has_llm=True,
        has_llm_fallback=True,
        llm_api_key="primary-key",
        llm_base_url="https://primary.example",
        llm_model="gpt-5.5",
        llm_wire_api="chat_completions",
        llm_reasoning_effort="low",
        llm_max_output_tokens=6000,
        llm_fallback_api_key="fallback-key",
        llm_fallback_base_url="https://tokenrhythm.studio/v1",
        llm_fallback_model="deepseek-v4-flash",
        request_timeout=3,
    )
    monkeypatch.setattr(llm_module, "settings", fake_settings)
    calls = []

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None) -> None:
            self.status_code = status_code
            self._payload = payload or {}
            self.text = ""

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError("failed")

        def json(self) -> dict:
            return self._payload

    def fake_post(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        if len(calls) == 1:
            return FakeResponse(503, {"error": {"message": "primary unavailable"}})
        return FakeResponse(
            200,
            {"choices": [{"message": {"content": "{\"ok\": true}"}}]},
        )

    monkeypatch.setattr(llm_module.requests, "post", fake_post)

    result = llm_module.LLMService().generate_json("system", "user")

    assert result == {"ok": True}
    assert calls[0]["url"] == "https://primary.example/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer primary-key"
    assert calls[1]["url"] == "https://tokenrhythm.studio/v1/chat/completions"
    assert calls[1]["headers"]["Authorization"] == "Bearer fallback-key"
    assert calls[1]["json"]["model"] == "deepseek-v4-flash"
