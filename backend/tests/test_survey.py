"""问卷包装模块的基础测试。"""

from backend.models import SurveyQuestion
from backend.services.analytics_service import (
    build_response,
    calculate_result_type,
    summarize_responses,
    validate_answers,
)
from backend.services.survey_service import (
    _validate_wjx_url,
    build_wrapped_survey,
    parse_survey_text,
    parse_wjx_html,
)


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


def test_wrap_title_follows_theme_hint() -> None:
    survey = build_wrapped_survey(
        [SurveyQuestion("q1", "价格", options=["100", "200"])],
        "测试",
        "周末旅行决策风格",
        llm_service=FakeLLMService(),
    )
    assert survey.theme == "周末旅行决策风格"
    assert survey.survey_name == "周末旅行决策风格测评"


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
