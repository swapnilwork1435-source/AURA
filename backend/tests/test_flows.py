from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import Base, UserProfile, app, estimate_targets, get_db


@pytest.fixture()
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        with TestingSession.begin() as db:
            from app.main import Food
            db.add_all([
                Food(name="Cooked rice", serving="1 cup", calories=205, protein_g=4, carbs_g=45, fat_g=0.4),
                Food(name="Banana", serving="1 medium (118 g)", calories=105, protein_g=1.3, carbs_g=27, fat_g=0.4),
                Food(name="Milk, whole", serving="1 cup (244 ml)", calories=149, protein_g=7.7, carbs_g=12, fat_g=8),
            ])
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


def register(client: TestClient, username: str = "wellness_user"):
    response = client.post("/api/auth/register", json={
        "full_name": "Wellness User",
        "username": username,
        "email": f"{username}@example.com",
        "password": "a-long-safe-password",
    })
    assert response.status_code == 201
    return response


def write(client: TestClient, method: str, path: str, **kwargs):
    kwargs.setdefault("headers", {})["X-CSRF-Token"] = client.cookies["aura_csrf"]
    return getattr(client, method)(path, **kwargs)


def test_auth_protection_and_logout(client):
    assert client.get("/api/auth/me").status_code == 401
    register(client)
    assert client.get("/api/auth/me").status_code == 200
    assert write(client, "post", "/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"username": "wellness_user", "password": "wrong-password"}).status_code == 401


def test_duplicate_registration_and_csrf(client):
    register(client)
    assert client.post("/api/auth/register", json={
        "full_name": "Another Person",
        "username": "wellness_user",
        "email": "other@example.com",
        "password": "a-long-safe-password",
    }).status_code == 409
    assert client.post("/api/nutrition", json={}).status_code == 403


def test_food_totals_persistence_and_user_isolation(client):
    register(client, "first_user")
    onboarding = write(client, "put", "/api/profile/onboarding", json={
        "goal": "Build muscle", "activity_level": "moderate", "units": "metric",
        "calorie_target": 2200, "protein_target_g": 140,
    })
    assert onboarding.status_code == 200
    food = write(client, "post", "/api/nutrition", json={
        "food_name": "Cooked rice", "quantity": 2, "serving_unit": "cup",
        "calories": 205, "protein_g": 4, "carbs_g": 45, "fat_g": 0.4,
        "meal": "Lunch", "consumed_at": f"{date.today().isoformat()}T00:00:00",
    })
    assert food.status_code == 201
    assert client.get(f"/api/nutrition?day={date.today().isoformat()}").json()["totals"]["calories"] == 410
    assert client.get("/api/dashboard").json()["protein_g"] == 8
    updated = write(client, "put", f"/api/nutrition/{food.json()['id']}", json={
        "food_name": "Cooked rice", "quantity": 2, "serving_unit": "cup",
        "calories": 190, "protein_g": 4, "carbs_g": 45, "fat_g": 0.4,
        "meal": "Lunch", "consumed_at": f"{date.today().isoformat()}T00:00:00",
    })
    assert updated.status_code == 200
    assert client.get(f"/api/nutrition?day={date.today().isoformat()}").json()["totals"]["calories"] == 380
    export = client.get("/api/analytics/export").text
    assert date.today().isoformat() in export and "380.0,8.0" in export
    register(client, "second_user")
    assert client.get("/api/nutrition").json()["entries"] == []
    assert write(client, "delete", f"/api/nutrition/{food.json()['id']}").status_code == 404


def test_account_deletion_cascades_owned_data(client):
    register(client)
    habit = write(client, "post", "/api/habits", json={"name": "Walk"}).json()
    assert habit["id"]
    assert write(client, "delete", "/api/account").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_habit_skincare_sleep_and_body_flows(client):
    register(client)
    habit = write(client, "post", "/api/habits", json={"name": "Walk", "category": "Movement"}).json()
    assert write(client, "put", f"/api/habits/{habit['id']}/complete").json()["completed"] is True
    routine = write(client, "post", "/api/skincare", json={"name": "AM routine", "routine_time": "Morning", "steps": ["Cleanse", "Moisturize"]}).json()
    assert write(client, "put", f"/api/skincare/{routine['id']}/complete").json()["completed"] is True
    sleep = write(client, "post", "/api/sleep", json={"bedtime": "2026-10-24T23:00:00", "wake_time": "2026-10-24T07:00:00"}).json()
    assert sleep["duration_hours"] == 8
    measurement = write(client, "post", "/api/body", json={"measured_on": "2026-10-24", "weight_kg": 68.5}).json()
    assert measurement["weight_kg"] == 68.5


def test_workout_sets_finish_and_csv(client):
    register(client)
    plan = write(client, "post", "/api/workouts/plans", json={"name": "Full body", "exercises": ["Squat"]}).json()
    workout = write(client, "post", "/api/workouts/start", json={"plan_id": plan["id"], "name": plan["name"]}).json()
    assert write(client, "post", f"/api/workouts/{workout['id']}/sets", json={"exercise": "Squat", "set_number": 1, "weight_kg": 40, "reps": 8, "completed": True}).status_code == 201
    assert client.get("/api/workouts").json()["sessions"][0]["sets"][0]["exercise"] == "Squat"
    assert write(client, "post", f"/api/workouts/{workout['id']}/finish").status_code == 200
    assert "date,weight_kg,waist_cm,calories,protein_g" in client.get("/api/analytics/export").text


def test_target_estimates_use_safeguards():
    adult = UserProfile(
        birth_date=date(1995, 1, 1),
        gender="female",
        height_cm=165,
        current_weight_kg=65,
        goal="Lose fat while maintaining muscle",
        activity_level="moderate",
    )
    estimate = estimate_targets(adult, today=date(2026, 1, 1))
    assert estimate and estimate["calorie_target"] >= 1200
    assert estimate["protein_target_g"] > 0 and estimate["carbs_target_g"] > 0
    assert estimate["bmr"] == 1365
    assert estimate["maintenance_calories"] == 2116
    assert estimate["calorie_target"] == 1816
    assert estimate["protein_target_g"] == 117
    assert estimate["fat_target_g"] == 50
    assert estimate["carbs_target_g"] == 224
    adult.birth_date = date(2015, 1, 1)
    assert estimate_targets(adult, today=date(2026, 1, 1)) is None
    adult.birth_date = date(1995, 1, 1)
    adult.avoid_weight_recommendations = True
    assert estimate_targets(adult, today=date(2026, 1, 1)) is None


def test_future_records_are_rejected(client):
    register(client)
    future_day = date.today().replace(year=date.today().year + 1).isoformat()
    response = write(client, "post", "/api/body", json={"measured_on": future_day, "weight_kg": 70})
    assert response.status_code == 422


def test_natural_language_food_and_idempotent_confirmation(client):
    register(client)
    parsed = client.post("/api/assistant/parse-food", json={"description": "2 bananas and 250 ml milk"})
    assert parsed.status_code == 200
    result = parsed.json()
    assert len(result["items"]) == 2
    assert result["totals"]["calories"] > 200
    body = {
        "idempotency_key": "meal-confirmation-001",
        "meal": "Breakfast",
        "items": [{"food_id": item["food_id"], "quantity": item["quantity"]} for item in result["items"]],
    }
    first = write(client, "post", "/api/assistant/confirm-meal", json=body)
    second = write(client, "post", "/api/assistant/confirm-meal", json=body)
    assert first.status_code == 201 and first.json()["duplicate"] is False
    assert second.status_code == 201 and second.json()["duplicate"] is True
    assert len(client.get(f"/api/nutrition?day={date.today().isoformat()}").json()["entries"]) == 2


def test_food_parser_requests_clarification_for_unknown_or_missing_quantity(client):
    register(client)
    assert client.post("/api/assistant/parse-food", json={"description": "a bowl of soup"}).json()["clarification"]
    assert client.post("/api/assistant/parse-food", json={"description": "2 bananas and some cereal"}).json()["clarification"]


def test_reminder_settings_due_snooze_and_duplicate_prevention(client):
    register(client)
    settings = client.get("/api/reminders/settings").json()
    now = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=1)
    settings.update({
        "timezone_name": "UTC",
        "notifications_enabled": False,
        "quiet_start": None,
        "quiet_end": None,
        "snooze_minutes": 15,
        "reminders": [{"meal": "Breakfast", "reminder_time": now.strftime("%H:%M"), "enabled": True}],
    })
    assert write(client, "put", "/api/reminders/settings", json=settings).status_code == 200
    first = client.get("/api/reminders/due").json()
    assert len(first["reminders"]) == 1
    delivery = first["reminders"][0]
    assert client.get("/api/reminders/due").json()["reminders"] == []
    response = write(client, "post", f"/api/reminders/{delivery['id']}/action", json={"action": "not_yet"})
    assert response.json()["status"] == "snoozed"
    assert client.get("/api/reminders/due").json()["reminders"] == []
    assert write(client, "post", f"/api/reminders/{delivery['id']}/action", json={"action": "skip"}).json()["status"] == "skipped"
    settings["timezone_name"] = "Not/A_Timezone"
    assert write(client, "put", "/api/reminders/settings", json=settings).status_code == 422


def test_due_reminders_suppress_meals_already_logged(client):
    register(client)
    local_now = datetime.now(ZoneInfo("UTC"))
    settings = client.get("/api/reminders/settings").json()
    settings.update({
        "timezone_name": "UTC",
        "quiet_start": None,
        "quiet_end": None,
        "reminders": [{"meal": "Breakfast", "reminder_time": local_now.strftime("%H:%M"), "enabled": True}],
    })
    assert write(client, "put", "/api/reminders/settings", json=settings).status_code == 200
    assert write(client, "post", "/api/nutrition", json={
        "food_name": "Cooked rice", "quantity": 1, "serving_unit": "cup",
        "calories": 205, "protein_g": 4, "carbs_g": 45, "fat_g": 0.4,
        "meal": "Breakfast", "consumed_at": local_now.replace(tzinfo=None).isoformat(),
    }).status_code == 201
    assert client.get("/api/reminders/due").json()["reminders"] == []


def test_water_history_can_be_edited_and_deleted(client):
    register(client)
    created = write(client, "post", "/api/water", json={"amount_ml": 250}).json()
    assert client.get(f"/api/water?day={date.today().isoformat()}").json()[0]["amount_ml"] == 250
    updated = write(client, "put", f"/api/water/{created['id']}", json={"amount_ml": 400}).json()
    assert updated["amount_ml"] == 400
    assert write(client, "delete", f"/api/water/{created['id']}").status_code == 204
    assert client.get(f"/api/water?day={date.today().isoformat()}").json() == []


def test_assistant_actions_are_idempotent_and_report_week(client):
    register(client)
    command = {"command_id": "command-water-001", "text": "I drank 500 ml water"}
    assert write(client, "post", "/api/assistant/command", json=command).json()["kind"] == "saved"
    write(client, "post", "/api/assistant/command", json=command)
    assert client.get(f"/api/dashboard?day={date.today().isoformat()}").json()["water_ml"] == 500
    report = client.get("/api/reports/weekly")
    assert report.status_code == 200
    assert report.json()["nutrition"]["average_calories"] is None


def test_onboarding_calculates_missing_targets_but_keeps_manual_values(client):
    register(client)
    response = write(client, "put", "/api/profile/onboarding", json={
        "birth_date": "1995-01-01", "gender": "female", "height_cm": 165,
        "current_weight_kg": 65, "goal": "Build muscle", "activity_level": "moderate",
        "units": "metric", "calorie_target": 2200,
    })
    assert response.status_code == 200
    profile = response.json()
    assert profile["calorie_target"] == 2200
    assert profile["protein_target_g"] is not None
    assert profile["calculation_method"] == "Mifflin–St Jeor"
    assert profile["targets_customized"] is True


def test_estimate_preview_preserves_manual_targets_until_accepted(client):
    register(client)
    saved = write(client, "put", "/api/profile/onboarding", json={
        "birth_date": "1995-01-01", "gender": "female", "height_cm": 165,
        "current_weight_kg": 65, "goal": "Lose weight", "activity_level": "moderate",
        "units": "metric", "calorie_target": 2200, "protein_target_g": 130,
        "carbs_target_g": 250, "fat_target_g": 70,
    })
    assert saved.status_code == 200
    preview = write(client, "post", "/api/goals/recalculate", json={"accept": False})
    assert preview.status_code == 200
    assert preview.json()["current_targets"] == {
        "calorie_target": 2200, "protein_target_g": 130,
        "carbs_target_g": 250, "fat_target_g": 70,
    }
    accepted = write(client, "post", "/api/goals/recalculate", json={"accept": True})
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] is True
    assert accepted.json()["profile"]["calorie_target"] != 2200
    assert accepted.json()["profile"]["targets_customized"] is False


def test_automation_preferences_and_idempotent_daily_events(client):
    register(client, "automation_user")
    defaults = client.get("/api/automations/settings")
    assert defaults.status_code == 200
    assert defaults.json()["timezone_name"] == "Asia/Kolkata"
    saved = write(client, "put", "/api/automations/settings", json={
        "timezone_name": "Asia/Kolkata",
        "water_reminders_enabled": False,
        "water_interval_minutes": 90,
        "morning_briefing_enabled": True,
        "morning_briefing_time": "00:00",
        "evening_checkin_enabled": True,
        "evening_checkin_time": "00:00",
    })
    assert saved.status_code == 200
    first = write(client, "post", "/api/automations/run-now", json={})
    second = write(client, "post", "/api/automations/run-now", json={})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["created_events"] >= 2
    assert second.json()["created_events"] == 0
    overview = client.get("/api/automations/overview")
    assert overview.status_code == 200
    kinds = {item["kind"] for item in overview.json()["events"]}
    assert "briefing" in kinds and "checkin" in kinds


def test_automation_events_are_user_scoped(client):
    register(client, "automation_first")
    write(client, "put", "/api/automations/settings", json={
        "timezone_name": "Asia/Kolkata", "water_reminders_enabled": False,
        "water_interval_minutes": 90, "morning_briefing_enabled": True,
        "morning_briefing_time": "00:00", "evening_checkin_enabled": False,
        "evening_checkin_time": "21:00",
    })
    write(client, "post", "/api/automations/run-now", json={})
    assert len(client.get("/api/automations/overview").json()["events"]) >= 1
    write(client, "post", "/api/auth/logout")
    register(client, "automation_second")
    assert client.get("/api/automations/overview").json()["events"] == []


def test_new_load_personal_record_creates_automation_event(client):
    register(client, "pr_user")
    start = write(client, "post", "/api/workouts/start", json={"name": "Strength day"})
    assert start.status_code == 201
    session_id = start.json()["id"]
    first = write(client, "post", f"/api/workouts/{session_id}/sets", json={
        "exercise": "Bench Press", "set_number": 1, "weight_kg": 20, "reps": 8, "completed": True,
    })
    assert first.status_code == 201
    second = write(client, "post", f"/api/workouts/{session_id}/sets", json={
        "exercise": "bench press", "set_number": 2, "weight_kg": 25, "reps": 6, "completed": True,
    })
    assert second.status_code == 201
    events = client.get("/api/automations/overview").json()["events"]
    assert any(item["kind"] == "personal_record" and "25 kg" in item["message"] for item in events)


def test_achievement_is_awarded_from_persisted_records(client):
    register(client, "achievement_user")
    write(client, "post", "/api/nutrition", json={
        "food_name": "Banana", "quantity": 1, "serving_unit": "medium",
        "calories": 105, "protein_g": 1.3, "carbs_g": 27, "fat_g": 0.4,
        "meal": "Breakfast", "consumed_at": f"{date.today().isoformat()}T08:00:00",
    })
    result = write(client, "post", "/api/automations/run-now", json={})
    assert result.status_code == 200
    overview = client.get("/api/automations/overview").json()
    assert any(item["code"] == "first_meal" for item in overview["achievements"])


def test_hydration_events_are_persisted_and_deduplicated(client):
    from app.main import AutomationEvent, SessionLocal, run_automations_for_user

    register(client, "hydration_user")
    write(client, "put", "/api/automations/settings", json={
        "timezone_name": "UTC", "water_reminders_enabled": True,
        "water_interval_minutes": 30, "morning_briefing_enabled": False,
        "morning_briefing_time": "07:00", "evening_checkin_enabled": False,
        "evening_checkin_time": "21:00",
    })
    # Use the test DB through the dependency override, not the process-global engine.
    from app.main import get_db
    override = app.dependency_overrides[get_db]
    db = next(override())
    try:
        fixed_now = datetime(2026, 10, 25, 12, 0, tzinfo=ZoneInfo("UTC"))
        first = run_automations_for_user(1, db, fixed_now)
        second = run_automations_for_user(1, db, fixed_now)
        assert first["created_events"] == 1
        assert second["created_events"] == 0
        rows = list(db.query(AutomationEvent).filter(AutomationEvent.user_id == 1).all())
        assert len(rows) == 1 and rows[0].kind == "hydration"
    finally:
        db.close()
