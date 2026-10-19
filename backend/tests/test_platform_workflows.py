from backend.models import WrappedQuestion, WrappedSurvey
from backend.storage.database import ResearchDatabase


def build_survey() -> WrappedSurvey:
    return WrappedSurvey(
        survey_name="测试问卷",
        theme="测试主题",
        tagline="测试副标题",
        intro="测试介绍",
        disclosure="测试说明",
        result_types=[{"name": "类型 A", "description": "类型说明"}],
        questions=[
            WrappedQuestion(
                question_id="q1",
                public_text="你喜欢什么？",
                source_text="原始问题：你喜欢什么？",
                question_type="single_choice",
                options=["阅读", "运动"],
            )
        ],
    )


def test_rejected_collecting_survey_creates_edit_state_and_notification(tmp_path):
    database = ResearchDatabase(str(tmp_path / "workflow.db"))
    owner = database.register_tenant(username="owner", password="123456")
    platform = database.get_user_account("platform")
    assert platform
    survey_id = database.save_survey(
        build_survey(),
        status="collecting",
        tenant_id=owner["workspace"]["id"],
        created_by=owner["user"]["id"],
        moderation_status="pending",
    )

    reviewed = database.review_survey(
        survey_id,
        int(platform["id"]),
        approved=False,
        note="题目内容需要补充说明。",
    )

    assert reviewed
    assert reviewed["status"] == "draft"
    assert reviewed["moderation_status"] == "rejected"
    assert reviewed["moderation_note"] == "题目内容需要补充说明。"
    notifications = database.list_unread_notifications(int(owner["user"]["id"]))
    assert notifications[0]["survey_id"] == survey_id
    assert "不符合平台规定" in notifications[0]["content"]
    detail = database.get_platform_review_detail(survey_id)
    assert detail and detail["questions"][0]["options"] == ["阅读", "运动"]

    database.update_survey_content(survey_id, build_survey())
    assert database.get_survey(survey_id)["moderation_status"] == "pending"


def test_freeze_invalidates_sessions_and_unfreeze_allows_login(tmp_path):
    database = ResearchDatabase(str(tmp_path / "freeze.db"))
    owner = database.register_tenant(username="owner", password="123456")
    login = database.authenticate_admin("owner", "123456")
    assert login
    database.update_user_status(int(owner["user"]["id"]), False)
    assert database.get_admin_session(login["token"]) is None
    assert database.get_user_account("owner")["is_active"] == 0

    database.update_user_status(int(owner["user"]["id"]), True)
    assert database.authenticate_admin("owner", "123456")


def test_announcements_publish_and_read_state(tmp_path):
    database = ResearchDatabase(str(tmp_path / "announcement.db"))
    owner = database.register_tenant(username="owner", password="123456")
    platform = database.get_user_account("platform")
    assert platform
    announcement = database.create_announcement("服务升级", "平台将在今晚维护。", int(platform["id"]), "published")
    items = database.list_announcements(user_id=int(owner["user"]["id"]))
    assert items[0]["id"] == announcement["id"]
    assert not items[0]["is_read"]
    assert database.mark_all_announcements_read(int(owner["user"]["id"])) == 1
    assert database.list_announcements(user_id=int(owner["user"]["id"]))[0]["is_read"]
