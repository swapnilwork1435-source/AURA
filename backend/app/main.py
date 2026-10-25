from __future__ import annotations

import csv
import io
import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.nutrition import parse_food_description


APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("AURA_DATA_DIR", APP_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("AURA_DATABASE_URL", f"sqlite:///{DATA_DIR / 'aura.db'}")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
password_hasher = PasswordHasher()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(connection, _record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class UserProfile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(30))
    height_cm: Mapped[float | None] = mapped_column(Float)
    current_weight_kg: Mapped[float | None] = mapped_column(Float)
    target_weight_kg: Mapped[float | None] = mapped_column(Float)
    goal: Mapped[str] = mapped_column(String(50), default="Improve general fitness")
    activity_level: Mapped[str] = mapped_column(String(30), default="moderate")
    units: Mapped[str] = mapped_column(String(10), default="metric")
    calorie_target: Mapped[int | None] = mapped_column(Integer)
    protein_target_g: Mapped[int | None] = mapped_column(Integer)
    carbs_target_g: Mapped[int | None] = mapped_column(Integer)
    fat_target_g: Mapped[int | None] = mapped_column(Integer)
    water_target_ml: Mapped[int] = mapped_column(Integer, default=2500)
    avoid_weight_recommendations: Mapped[bool] = mapped_column(Boolean, default=False)
    targets_customized: Mapped[bool] = mapped_column(Boolean, default=False)
    calculation_method: Mapped[str | None] = mapped_column(String(80))
    calculation_inputs: Mapped[str | None] = mapped_column(Text)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime)
    surplus_kcal: Mapped[int] = mapped_column(Integer, default=200)
    deficit_kcal: Mapped[int] = mapped_column(Integer, default=300)
    training_days_per_week: Mapped[int | None] = mapped_column(Integer)
    body_fat_percent: Mapped[float | None] = mapped_column(Float)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class Food(Base):
    __tablename__ = "foods"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    serving: Mapped[str] = mapped_column(String(80))
    calories: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    estimated: Mapped[bool] = mapped_column(Boolean, default=True)


class FoodEntry(Base):
    __tablename__ = "food_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    food_name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[float] = mapped_column(Float)
    serving_unit: Mapped[str] = mapped_column(String(80))
    calories: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    meal: Mapped[str] = mapped_column(String(30), index=True)
    consumed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    notes: Mapped[str | None] = mapped_column(Text)


class MealSubmission(Base):
    __tablename__ = "meal_submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    entries_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)


class AssistantCommand(Base):
    __tablename__ = "assistant_commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    command_id: Mapped[str] = mapped_column(String(80))
    response_json: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("user_id", "command_id"),)


class ReminderPreference(Base):
    __tablename__ = "reminder_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    timezone_name: Mapped[str] = mapped_column(String(80), default="Asia/Kolkata")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_start: Mapped[str | None] = mapped_column(String(5))
    quiet_end: Mapped[str | None] = mapped_column(String(5))
    snooze_minutes: Mapped[int] = mapped_column(Integer, default=15)


class MealReminder(Base):
    __tablename__ = "meal_reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meal: Mapped[str] = mapped_column(String(30))
    reminder_time: Mapped[str] = mapped_column(String(5))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("user_id", "meal"),)


class ReminderDelivery(Base):
    __tablename__ = "reminder_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meal: Mapped[str] = mapped_column(String(30))
    local_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="sent")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("user_id", "meal", "local_date"),)


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    exercises: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("workout_plans.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class WorkoutSet(Base):
    __tablename__ = "workout_sets"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exercise: Mapped[str] = mapped_column(String(100))
    set_number: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[float] = mapped_column(Float, default=0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class BodyMeasurement(Base):
    __tablename__ = "body_measurements"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    measured_on: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    waist_cm: Mapped[float | None] = mapped_column(Float)
    chest_cm: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)


class Habit(Base):
    __tablename__ = "habits"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(50), default="Wellness")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class HabitCompletion(Base):
    __tablename__ = "habit_completions"
    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    completed_on: Mapped[date] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("habit_id", "completed_on"),)


class WaterEntry(Base):
    __tablename__ = "water_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount_ml: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class SleepEntry(Base):
    __tablename__ = "sleep_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bedtime: Mapped[datetime] = mapped_column(DateTime)
    wake_time: Mapped[datetime] = mapped_column(DateTime)
    quality: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class SkincareRoutine(Base):
    __tablename__ = "skincare_routines"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    routine_time: Mapped[str] = mapped_column(String(20), default="Morning")
    steps: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SkincareCompletion(Base):
    __tablename__ = "skincare_completions"
    id: Mapped[int] = mapped_column(primary_key=True)
    routine_id: Mapped[int] = mapped_column(ForeignKey("skincare_routines.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    completed_on: Mapped[date] = mapped_column(Date, index=True)
    __table_args__ = (UniqueConstraint("routine_id", "completed_on"),)


class RegisterInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,32}$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginInput(BaseModel):
    username: str
    password: str


class OnboardingInput(BaseModel):
    birth_date: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    height_cm: float | None = Field(default=None, gt=50, lt=275)
    current_weight_kg: float | None = Field(default=None, gt=20, lt=500)
    target_weight_kg: float | None = Field(default=None, gt=20, lt=500)
    goal: str = Field(default="Improve general fitness", max_length=50)
    activity_level: str = Field(default="moderate", pattern=r"^(sedentary|light|moderate|active|very_active)$")
    units: str = Field(default="metric", pattern=r"^(metric|imperial)$")
    calorie_target: int | None = Field(default=None, ge=800, le=10000)
    protein_target_g: int | None = Field(default=None, ge=0, le=1000)
    carbs_target_g: int | None = Field(default=None, ge=0, le=1500)
    fat_target_g: int | None = Field(default=None, ge=0, le=500)
    water_target_ml: int = Field(default=2500, ge=250, le=10000)
    avoid_weight_recommendations: bool = False
    surplus_kcal: int = Field(default=200, ge=0, le=500)
    deficit_kcal: int = Field(default=300, ge=0, le=750)
    training_days_per_week: int | None = Field(default=None, ge=0, le=7)
    body_fat_percent: float | None = Field(default=None, gt=2, lt=75)


class TargetRecalculationInput(BaseModel):
    accept: bool = False
    surplus_kcal: int = Field(default=200, ge=0, le=500)
    deficit_kcal: int = Field(default=300, ge=0, le=750)


class ParsedFoodInput(BaseModel):
    description: str = Field(min_length=1, max_length=500)


class ConfirmedFoodItem(BaseModel):
    food_id: int
    quantity: float = Field(gt=0, le=1000)


class ConfirmMealInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    meal: str = Field(min_length=1, max_length=30)
    items: list[ConfirmedFoodItem] = Field(min_length=1, max_length=12)
    consumed_at: datetime | None = None
    reminder_id: int | None = None


class ReminderItemInput(BaseModel):
    meal: str = Field(min_length=1, max_length=30)
    reminder_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    enabled: bool = True


class ReminderPreferencesInput(BaseModel):
    timezone_name: str = Field(min_length=1, max_length=80)
    notifications_enabled: bool = False
    quiet_start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    snooze_minutes: int = Field(default=15, ge=5, le=120)
    reminders: list[ReminderItemInput] = Field(max_length=12)


class ReminderActionInput(BaseModel):
    action: str = Field(pattern=r"^(open_log|not_yet|snooze|skip|dismiss)$")
    snooze_minutes: int | None = Field(default=None, ge=5, le=120)


class AssistantCommandInput(BaseModel):
    command_id: str = Field(min_length=8, max_length=80)
    text: str = Field(min_length=1, max_length=500)


class FoodInput(BaseModel):
    food_name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(gt=0, le=1000)
    serving_unit: str = Field(min_length=1, max_length=80)
    calories: float = Field(ge=0, le=10000)
    protein_g: float = Field(ge=0, le=1000)
    carbs_g: float = Field(ge=0, le=1500)
    fat_g: float = Field(ge=0, le=500)
    meal: str = Field(min_length=1, max_length=30)
    consumed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("consumed_at")
    @classmethod
    def reject_future_food(cls, value):
        if value and value.tzinfo:
            value = value.astimezone().replace(tzinfo=None)
        if value and value > datetime.now():
            raise ValueError("Food entries cannot be dated in the future.")
        return value


class WorkoutPlanInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    exercises: list[str] = Field(default_factory=list, max_length=50)


class WorkoutStartInput(BaseModel):
    plan_id: int | None = None
    name: str = Field(min_length=1, max_length=100)


class SetInput(BaseModel):
    exercise: str = Field(min_length=1, max_length=100)
    set_number: int = Field(ge=1, le=100)
    weight_kg: float = Field(ge=0, le=1500)
    reps: int = Field(ge=0, le=1000)
    completed: bool = False


class MeasurementInput(BaseModel):
    measured_on: date = Field(default_factory=date.today)
    weight_kg: float | None = Field(default=None, gt=20, lt=500)
    waist_cm: float | None = Field(default=None, gt=20, lt=300)
    chest_cm: float | None = Field(default=None, gt=20, lt=300)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("measured_on")
    @classmethod
    def reject_future_measurement(cls, value):
        if value > date.today():
            raise ValueError("Measurements cannot be dated in the future.")
        return value


class HabitInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(default="Wellness", max_length=50)


class WaterInput(BaseModel):
    amount_ml: int = Field(gt=0, le=5000)
    recorded_at: datetime | None = None

    @field_validator("recorded_at")
    @classmethod
    def reject_future_water(cls, value):
        if value and value.tzinfo:
            value = value.astimezone().replace(tzinfo=None)
        if value and value > datetime.now():
            raise ValueError("Water entries cannot be dated in the future.")
        return value


class SleepInput(BaseModel):
    bedtime: datetime
    wake_time: datetime
    quality: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("bedtime", "wake_time")
    @classmethod
    def normalize_sleep_time(cls, value):
        return value.astimezone().replace(tzinfo=None) if value.tzinfo else value


class RoutineInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    routine_time: str = Field(default="Morning", pattern=r"^(Morning|Evening|Anytime)$")
    steps: list[str] = Field(default_factory=list, max_length=30)


def prevent_future_day(day: date):
    if day > date.today():
        raise HTTPException(status_code=422, detail="Records cannot be created for a future date.")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias="aura_session")] = None,
) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="Please sign in.")
    auth = db.get(AuthSession, session_token)
    if not auth or auth.expires_at < utc_now():
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    user = db.get(User, auth.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Session is no longer valid.")
    return user


def require_csrf(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    session_token: Annotated[str | None, Cookie(alias="aura_session")] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias="aura_csrf")] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> User:
    auth = db.get(AuthSession, session_token) if session_token else None
    if not auth or not csrf_cookie or not csrf_header or not secrets.compare_digest(auth.csrf_token, csrf_cookie) or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
WriteUser = Annotated[User, Depends(require_csrf)]
Db = Annotated[Session, Depends(get_db)]

@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    profile_columns = {column["name"] for column in inspect(engine).get_columns("profiles")}
    legacy_profile_columns = {
        "targets_customized": "BOOLEAN NOT NULL DEFAULT 0",
        "calculation_method": "VARCHAR(80)",
        "calculation_inputs": "TEXT",
        "calculated_at": "DATETIME",
        "surplus_kcal": "INTEGER NOT NULL DEFAULT 200",
        "deficit_kcal": "INTEGER NOT NULL DEFAULT 300",
        "training_days_per_week": "INTEGER",
        "body_fat_percent": "FLOAT",
    }
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            for column, declaration in legacy_profile_columns.items():
                if column not in profile_columns:
                    connection.exec_driver_sql(f"ALTER TABLE profiles ADD COLUMN {column} {declaration}")
            connection.exec_driver_sql(
                "UPDATE profiles SET targets_customized = 1 WHERE "
                "targets_customized = 0 AND "
                "(calorie_target IS NOT NULL OR protein_target_g IS NOT NULL OR "
                "carbs_target_g IS NOT NULL OR fat_target_g IS NOT NULL)"
            )
    with SessionLocal.begin() as db:
        if db.scalar(select(func.count(Food.id))) == 0:
            db.add_all(Food(name=n, serving=s, calories=c, protein_g=p, carbs_g=ch, fat_g=f) for n, s, c, p, ch, f in SEED_FOODS)
    yield


app = FastAPI(title="AURA API", version="1.0.0", description="Local-first personal wellness platform", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("AURA_FRONTEND_ORIGIN", "http://127.0.0.1:5173"), "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

SEED_FOODS = [
    ("Chapati, cooked", "1 medium (40 g)", 120, 3.5, 18, 3),
    ("Rice, cooked", "1 cup (158 g)", 205, 4.3, 45, 0.4),
    ("Dal, cooked", "1 cup (198 g)", 230, 18, 40, 1),
    ("Poha, prepared", "1 cup (150 g)", 250, 5, 45, 6),
    ("Idli", "2 pieces (100 g)", 130, 4, 28, 0.5),
    ("Dosa, plain", "1 medium (100 g)", 168, 4, 29, 3.7),
    ("Milk, whole", "1 cup (244 ml)", 149, 7.7, 12, 8),
    ("Curd, plain", "1 cup (245 g)", 149, 8.5, 11.4, 8),
    ("Paneer", "100 g", 265, 18.3, 1.2, 20.8),
    ("Egg, whole", "1 large (50 g)", 72, 6.3, 0.4, 4.8),
    ("Banana", "1 medium (118 g)", 105, 1.3, 27, 0.4),
    ("Oats, dry", "40 g", 152, 5.3, 27, 2.7),
    ("Peanut butter", "1 tbsp (16 g)", 94, 3.6, 3.2, 8),
    ("Soya chunks, cooked", "100 g", 173, 18, 20, 0.5),
    ("Chickpeas, cooked", "1 cup (164 g)", 269, 14.5, 45, 4.2),
    ("Rajma, cooked", "1 cup (177 g)", 225, 15, 40, 0.9),
    ("Mixed vegetables, cooked", "1 cup (180 g)", 120, 4, 22, 2),
    ("Chicken breast, cooked", "100 g", 165, 31, 0, 3.6),
    ("Fish, cooked", "100 g", 160, 25, 0, 6),
    ("Samosa, vegetable", "1 medium (100 g)", 260, 5, 31, 13),
]


def estimate_targets(profile: UserProfile, today: date | None = None) -> dict | None:
    """Estimate calorie and macro targets; these are not measured metabolism or medical advice."""
    today = today or date.today()
    if profile.avoid_weight_recommendations or not profile.birth_date or not profile.height_cm or not profile.current_weight_kg:
        return None
    age = today.year - profile.birth_date.year - ((today.month, today.day) < (profile.birth_date.month, profile.birth_date.day))
    if not 18 <= age <= 80 or profile.gender not in {"male", "female"}:
        return None
    sex_constant = 5 if profile.gender == "male" else -161
    bmr = 10 * profile.current_weight_kg + 6.25 * profile.height_cm - 5 * age + sex_constant
    activity_factors = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}
    activity_factor = activity_factors[profile.activity_level]
    maintenance = bmr * activity_factor
    if profile.goal in {"Build muscle", "Gain weight", "Weight gain", "Muscle gain"}:
        calories = maintenance + (profile.surplus_kcal if profile.surplus_kcal is not None else 200)
    elif profile.goal in {"Lose weight", "Lose fat while maintaining muscle", "Fat loss"}:
        calories = maintenance - (profile.deficit_kcal if profile.deficit_kcal is not None else 300)
    else:
        calories = maintenance
    calories = round(calories)
    if calories < 1200:
        return None
    protein_factor = 1.8 if profile.goal in {"Build muscle", "Gain weight", "Weight gain", "Muscle gain", "Lose weight", "Lose fat while maintaining muscle", "Fat loss", "Recomposition"} else 1.4
    protein = round(profile.current_weight_kg * protein_factor)
    fat = round(max(profile.current_weight_kg * 0.6, calories * 0.25 / 9))
    carbs = max(0, round((calories - protein * 4 - fat * 9) / 4))
    return {
        "bmr": round(bmr),
        "maintenance_calories": round(maintenance),
        "calorie_target": calories,
        "protein_target_g": protein,
        "carbs_target_g": carbs,
        "fat_target_g": fat,
        "activity_factor": activity_factor,
        "method": "Mifflin–St Jeor",
        "inputs": {
            "age_years": age,
            "height_cm": profile.height_cm,
            "weight_kg": profile.current_weight_kg,
            "gender": profile.gender,
            "activity_level": profile.activity_level,
            "training_days_per_week": profile.training_days_per_week,
            "goal": profile.goal,
            "surplus_kcal": profile.surplus_kcal,
            "deficit_kcal": profile.deficit_kcal,
            "protein_g_per_kg": protein_factor,
            "fat_energy_fraction": 0.25,
        },
    }


def set_auth_cookies(response: Response, user: User, db: Session):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.add(AuthSession(token=token, csrf_token=csrf, user_id=user.id, expires_at=utc_now() + timedelta(days=14)))
    secure = os.getenv("AURA_COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie("aura_session", token, httponly=True, secure=secure, samesite="strict", max_age=14 * 86400, path="/")
    response.set_cookie("aura_csrf", csrf, httponly=False, secure=secure, samesite="strict", max_age=14 * 86400, path="/")


def profile_out(profile: UserProfile | None):
    if not profile:
        return None
    return {c.name: getattr(profile, c.name) for c in UserProfile.__table__.columns if c.name != "user_id"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterInput, response: Response, db: Db):
    if db.scalar(select(User).where((User.username == payload.username) | (User.email == payload.email.lower()))):
        raise HTTPException(status_code=409, detail="Username or email is already registered.")
    user = User(full_name=payload.full_name.strip(), username=payload.username, email=payload.email.lower(), password_hash=password_hasher.hash(payload.password))
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id))
    db.flush()
    set_auth_cookies(response, user, db)
    db.commit()
    return {"id": user.id, "full_name": user.full_name, "username": user.username, "email": user.email, "profile": profile_out(db.get(UserProfile, user.id))}


@app.post("/api/auth/login")
def login(payload: LoginInput, response: Response, db: Db):
    user = db.scalar(select(User).where((User.username == payload.username) | (User.email == payload.username.lower())))
    try:
        valid = bool(user and password_hasher.verify(user.password_hash, payload.password))
    except VerifyMismatchError:
        valid = False
    if not valid or not user:
        raise HTTPException(status_code=401, detail="Incorrect username/email or password.")
    set_auth_cookies(response, user, db)
    db.commit()
    return {"id": user.id, "full_name": user.full_name, "username": user.username, "email": user.email, "profile": profile_out(db.get(UserProfile, user.id))}


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response, db: Db, session_token: Annotated[str | None, Cookie(alias="aura_session")] = None):
    if session_token:
        auth = db.get(AuthSession, session_token)
        if auth:
            db.delete(auth)
            db.commit()
    response.delete_cookie("aura_session", path="/", samesite="strict")
    response.delete_cookie("aura_csrf", path="/", samesite="strict")
    response.status_code = 204
    return response


@app.get("/api/auth/me")
def me(user: CurrentUser, db: Db):
    return {"id": user.id, "full_name": user.full_name, "username": user.username, "email": user.email, "profile": profile_out(db.get(UserProfile, user.id))}


@app.put("/api/profile/onboarding")
def onboarding(payload: OnboardingInput, user: WriteUser, db: Db):
    profile = db.get(UserProfile, user.id)
    submitted = payload.model_dump()
    explicitly_set_targets = any(submitted[key] is not None for key in ("calorie_target", "protein_target_g", "carbs_target_g", "fat_target_g"))
    for key, value in submitted.items():
        setattr(profile, key, value)
    if explicitly_set_targets:
        profile.targets_customized = True
    estimate = estimate_targets(profile)
    if estimate:
        for field in ("calorie_target", "protein_target_g", "carbs_target_g", "fat_target_g"):
            if getattr(profile, field) is None:
                setattr(profile, field, estimate[field])
        profile.calculation_method = estimate["method"]
        profile.calculation_inputs = json.dumps(estimate)
        profile.calculated_at = utc_now()
    profile.onboarding_complete = True
    db.commit()
    return profile_out(profile)


@app.get("/api/goals/estimate")
def preview_goal_estimate(user: CurrentUser, db: Db):
    profile = db.get(UserProfile, user.id)
    estimate = estimate_targets(profile)
    return {
        "estimate": estimate,
        "targets_customized": profile.targets_customized,
        "current_targets": {
            field: getattr(profile, field)
            for field in ("calorie_target", "protein_target_g", "carbs_target_g", "fat_target_g")
        },
        "message": "Complete age, height, current weight, activity level and optional sex to estimate adult targets. Recommendations are skipped for minors or when you opt out."
        if estimate is None else "An estimate is ready. Review it and explicitly accept before replacing your current targets.",
    }


@app.post("/api/goals/recalculate")
def recalculate_goal_estimate(payload: TargetRecalculationInput, user: WriteUser, db: Db):
    profile = db.get(UserProfile, user.id)
    previous_surplus = profile.surplus_kcal
    previous_deficit = profile.deficit_kcal
    profile.surplus_kcal = payload.surplus_kcal
    profile.deficit_kcal = payload.deficit_kcal
    estimate = estimate_targets(profile)
    if not estimate:
        raise HTTPException(status_code=422, detail="A safe estimate is unavailable. Check required profile inputs or keep manually selected targets.")
    if payload.accept:
        for field in ("calorie_target", "protein_target_g", "carbs_target_g", "fat_target_g"):
            setattr(profile, field, estimate[field])
        profile.targets_customized = False
        profile.calculation_method = estimate["method"]
        profile.calculation_inputs = json.dumps(estimate)
        profile.calculated_at = utc_now()
        db.commit()
    else:
        profile.surplus_kcal = previous_surplus
        profile.deficit_kcal = previous_deficit
    return {
        "estimate": estimate,
        "accepted": payload.accept,
        "targets_customized": profile.targets_customized,
        "current_targets": {field: getattr(profile, field) for field in ("calorie_target", "protein_target_g", "carbs_target_g", "fat_target_g")},
        "profile": profile_out(profile),
    }


DEFAULT_REMINDERS = [
    ("Breakfast", "08:00"),
    ("Morning snack", "10:30"),
    ("Lunch", "13:00"),
    ("Evening snack", "16:30"),
    ("Dinner", "19:30"),
]


def get_or_create_reminder_preferences(user: User, db: Session) -> ReminderPreference:
    preferences = db.get(ReminderPreference, user.id)
    if preferences is None:
        preferences = ReminderPreference(user_id=user.id)
        db.add(preferences)
        db.flush()
    existing = {item.meal for item in db.scalars(select(MealReminder).where(MealReminder.user_id == user.id))}
    for meal, reminder_time in DEFAULT_REMINDERS:
        if meal not in existing:
            db.add(MealReminder(user_id=user.id, meal=meal, reminder_time=reminder_time))
    db.flush()
    return preferences


def reminder_preferences_output(preferences: ReminderPreference, reminders: list[MealReminder]):
    return {
        "timezone_name": preferences.timezone_name,
        "notifications_enabled": preferences.notifications_enabled,
        "quiet_start": preferences.quiet_start,
        "quiet_end": preferences.quiet_end,
        "snooze_minutes": preferences.snooze_minutes,
        "reminders": [{"meal": reminder.meal, "reminder_time": reminder.reminder_time, "enabled": reminder.enabled} for reminder in reminders],
    }


@app.get("/api/reminders/settings")
def get_reminder_settings(user: CurrentUser, db: Db):
    preferences = get_or_create_reminder_preferences(user, db)
    db.commit()
    reminders = list(db.scalars(select(MealReminder).where(MealReminder.user_id == user.id).order_by(MealReminder.id)))
    return reminder_preferences_output(preferences, reminders)


@app.put("/api/reminders/settings")
def save_reminder_settings(payload: ReminderPreferencesInput, user: WriteUser, db: Db):
    try:
        ZoneInfo(payload.timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Use a valid IANA time zone, such as Asia/Kolkata.") from exc
    if bool(payload.quiet_start) != bool(payload.quiet_end):
        raise HTTPException(status_code=422, detail="Set both quiet-hour times, or clear both.")
    preferences = get_or_create_reminder_preferences(user, db)
    preferences.timezone_name = payload.timezone_name
    preferences.notifications_enabled = payload.notifications_enabled
    preferences.quiet_start = payload.quiet_start
    preferences.quiet_end = payload.quiet_end
    preferences.snooze_minutes = payload.snooze_minutes
    existing = {item.meal: item for item in db.scalars(select(MealReminder).where(MealReminder.user_id == user.id))}
    for item in payload.reminders:
        reminder = existing.get(item.meal)
        if reminder is None:
            reminder = MealReminder(user_id=user.id, meal=item.meal, reminder_time=item.reminder_time, enabled=item.enabled)
            db.add(reminder)
        else:
            reminder.reminder_time = item.reminder_time
            reminder.enabled = item.enabled
    retained = {item.meal for item in payload.reminders}
    for meal, reminder in existing.items():
        if meal not in retained:
            db.delete(reminder)
    db.commit()
    return reminder_preferences_output(preferences, list(db.scalars(select(MealReminder).where(MealReminder.user_id == user.id).order_by(MealReminder.id))))


def is_quiet_time(local_time: time, quiet_start: str | None, quiet_end: str | None) -> bool:
    if not quiet_start or not quiet_end:
        return False
    start = time.fromisoformat(quiet_start)
    end = time.fromisoformat(quiet_end)
    if start == end:
        return True
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


@app.get("/api/reminders/due")
def due_reminders(user: CurrentUser, db: Db):
    preferences = get_or_create_reminder_preferences(user, db)
    try:
        local_now = datetime.now(ZoneInfo(preferences.timezone_name))
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="The saved reminder time zone is invalid.") from exc
    now_utc = utc_now()
    local_day = local_now.date().isoformat()
    if is_quiet_time(local_now.time().replace(tzinfo=None), preferences.quiet_start, preferences.quiet_end):
        db.commit()
        return {"reminders": [], "notifications_enabled": preferences.notifications_enabled}
    reminders = list(db.scalars(select(MealReminder).where(MealReminder.user_id == user.id, MealReminder.enabled.is_(True))))
    due = []
    for reminder in reminders:
        delivery = db.scalar(select(ReminderDelivery).where(
            ReminderDelivery.user_id == user.id,
            ReminderDelivery.meal == reminder.meal,
            ReminderDelivery.local_date == local_day,
        ))
        if delivery and delivery.status == "snoozed":
            if not delivery.snooze_until or delivery.snooze_until > now_utc:
                continue
            delivery.status = "sent"
            delivery.snooze_until = None
            delivery.sent_at = now_utc
            due.append(delivery)
            continue
        if delivery:
            continue

        scheduled = datetime.combine(local_now.date(), time.fromisoformat(reminder.reminder_time))
        if not scheduled <= local_now.replace(tzinfo=None) < scheduled + timedelta(minutes=15):
            continue
        logged = db.scalar(select(FoodEntry.id).where(
            FoodEntry.user_id == user.id,
            FoodEntry.meal == reminder.meal,
            FoodEntry.consumed_at >= datetime.combine(local_now.date(), time.min),
            FoodEntry.consumed_at < datetime.combine(local_now.date() + timedelta(days=1), time.min),
        ).limit(1))
        if logged:
            continue
        delivery = ReminderDelivery(user_id=user.id, meal=reminder.meal, local_date=local_day, status="sent", sent_at=now_utc)
        db.add(delivery)
        try:
            db.flush()
            due.append(delivery)
        except IntegrityError:
            db.rollback()
            return []
    db.commit()
    return {
        "reminders": [{"id": item.id, "meal": item.meal, "local_date": item.local_date, "status": item.status, "snooze_minutes": preferences.snooze_minutes} for item in due],
        "notifications_enabled": preferences.notifications_enabled,
    }


@app.post("/api/reminders/{delivery_id}/action")
def reminder_action(delivery_id: int, payload: ReminderActionInput, user: WriteUser, db: Db):
    delivery = db.scalar(select(ReminderDelivery).where(ReminderDelivery.id == delivery_id, ReminderDelivery.user_id == user.id))
    if not delivery:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    if payload.action == "open_log":
        return {"id": delivery.id, "status": delivery.status, "meal": delivery.meal}
    if payload.action in {"not_yet", "snooze"}:
        preferences = get_or_create_reminder_preferences(user, db)
        delivery.status = "snoozed"
        delivery.snooze_until = utc_now() + timedelta(minutes=payload.snooze_minutes or preferences.snooze_minutes)
    elif payload.action == "skip":
        delivery.status = "skipped"
        delivery.snooze_until = None
    else:
        delivery.status = "dismissed"
        delivery.snooze_until = None
    db.commit()
    return {"id": delivery.id, "status": delivery.status, "meal": delivery.meal}


@app.get("/api/foods")
def foods(user: CurrentUser, db: Db, q: str = Query(default="", max_length=100)):
    return [{"id": f.id, "name": f.name, "serving": f.serving, "calories": f.calories, "protein_g": f.protein_g, "carbs_g": f.carbs_g, "fat_g": f.fat_g, "estimated": f.estimated} for f in db.scalars(select(Food).where(Food.name.ilike(f"%{q}%")).order_by(Food.name).limit(100))]


def food_dict(row: FoodEntry):
    return {"id": row.id, "food_name": row.food_name, "quantity": row.quantity, "serving_unit": row.serving_unit, "calories": row.calories, "protein_g": row.protein_g, "carbs_g": row.carbs_g, "fat_g": row.fat_g, "meal": row.meal, "consumed_at": row.consumed_at.isoformat(), "notes": row.notes}


@app.post("/api/assistant/parse-food")
def assistant_parse_food(payload: ParsedFoodInput, user: CurrentUser, db: Db):
    catalog = list(db.scalars(select(Food).order_by(Food.name)))
    return parse_food_description(payload.description, catalog)


@app.post("/api/assistant/confirm-meal", status_code=201)
def assistant_confirm_meal(payload: ConfirmMealInput, user: WriteUser, db: Db):
    submission = db.scalar(select(MealSubmission).where(
        MealSubmission.user_id == user.id,
        MealSubmission.idempotency_key == payload.idempotency_key,
    ))
    if submission:
        ids = json.loads(submission.entries_json)
        entries = list(db.scalars(select(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.id.in_(ids))))
        return {"entries": [food_dict(entry) for entry in entries], "duplicate": True}

    foods_by_id = {
        food.id: food for food in db.scalars(select(Food).where(Food.id.in_([item.food_id for item in payload.items])))
    }
    if len(foods_by_id) != len({item.food_id for item in payload.items}):
        raise HTTPException(status_code=422, detail="One or more selected foods are no longer available.")
    consumed_at = payload.consumed_at or datetime.now()
    if consumed_at.tzinfo:
        consumed_at = consumed_at.astimezone().replace(tzinfo=None)
    if consumed_at > datetime.now():
        raise HTTPException(status_code=422, detail="Food entries cannot be dated in the future.")
    if payload.reminder_id is not None:
        reminder = db.scalar(select(ReminderDelivery).where(
            ReminderDelivery.id == payload.reminder_id,
            ReminderDelivery.user_id == user.id,
        ))
        if not reminder or reminder.meal != payload.meal:
            raise HTTPException(status_code=404, detail="Meal reminder not found.")
    submission = MealSubmission(user_id=user.id, idempotency_key=payload.idempotency_key, entries_json="[]")
    db.add(submission)
    try:
        db.flush()
        entries = []
        for item in payload.items:
            food = foods_by_id[item.food_id]
            entry = FoodEntry(
                user_id=user.id,
                food_name=food.name,
                quantity=item.quantity,
                serving_unit=food.serving,
                calories=food.calories,
                protein_g=food.protein_g,
                carbs_g=food.carbs_g,
                fat_g=food.fat_g,
                meal=payload.meal,
                consumed_at=consumed_at,
                notes="Estimated values from AURA's local food catalogue.",
            )
            db.add(entry)
            entries.append(entry)
        db.flush()
        submission.entries_json = json.dumps([entry.id for entry in entries])
        active_delivery = reminder if payload.reminder_id is not None else db.scalar(select(ReminderDelivery).where(
            ReminderDelivery.user_id == user.id,
            ReminderDelivery.meal == payload.meal,
            ReminderDelivery.local_date == consumed_at.date().isoformat(),
        ))
        if active_delivery:
            active_delivery.status = "completed"
            active_delivery.snooze_until = None
        db.commit()
        return {"entries": [food_dict(entry) for entry in entries], "duplicate": False}
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(select(MealSubmission).where(
            MealSubmission.user_id == user.id,
            MealSubmission.idempotency_key == payload.idempotency_key,
        ))
        if not duplicate:
            raise
        ids = json.loads(duplicate.entries_json)
        entries = list(db.scalars(select(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.id.in_(ids))))
        return {"entries": [food_dict(entry) for entry in entries], "duplicate": True}


@app.get("/api/nutrition")
def nutrition(user: CurrentUser, db: Db, day: date = Query(default_factory=date.today)):
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    entries = list(db.scalars(select(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.consumed_at >= start, FoodEntry.consumed_at < end).order_by(FoodEntry.consumed_at.desc())))
    totals = {key: round(sum(getattr(e, key) * e.quantity for e in entries), 1) for key in ("calories", "protein_g", "carbs_g", "fat_g")}
    return {"date": day.isoformat(), "totals": totals, "entries": [food_dict(e) for e in entries]}


@app.post("/api/nutrition", status_code=201)
def add_food(payload: FoodInput, user: WriteUser, db: Db):
    values = payload.model_dump()
    values["consumed_at"] = values["consumed_at"] or datetime.now()
    row = FoodEntry(user_id=user.id, **values)
    db.add(row)
    db.commit()
    db.refresh(row)
    delivery = db.scalar(select(ReminderDelivery).where(
        ReminderDelivery.user_id == user.id,
        ReminderDelivery.meal == row.meal,
        ReminderDelivery.local_date == row.consumed_at.date().isoformat(),
    ))
    if delivery:
        delivery.status = "completed"
        delivery.snooze_until = None
        db.commit()
    return food_dict(row)


@app.put("/api/nutrition/{entry_id}")
def edit_food(entry_id: int, payload: FoodInput, user: WriteUser, db: Db):
    row = db.scalar(select(FoodEntry).where(FoodEntry.id == entry_id, FoodEntry.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="Food entry not found.")
    for key, value in payload.model_dump().items():
        if value is not None:
            setattr(row, key, value)
    db.commit()
    return food_dict(row)


@app.delete("/api/nutrition/{entry_id}", status_code=204)
def delete_food(entry_id: int, user: WriteUser, db: Db):
    row = db.scalar(select(FoodEntry).where(FoodEntry.id == entry_id, FoodEntry.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="Food entry not found.")
    db.delete(row)
    db.commit()


@app.get("/api/workouts")
def workouts(user: CurrentUser, db: Db):
    plans = list(db.scalars(select(WorkoutPlan).where(WorkoutPlan.user_id == user.id).order_by(WorkoutPlan.id.desc())))
    sessions = list(db.scalars(select(WorkoutSession).where(WorkoutSession.user_id == user.id).order_by(WorkoutSession.started_at.desc()).limit(30)))
    sets = list(db.scalars(select(WorkoutSet).where(WorkoutSet.user_id == user.id, WorkoutSet.session_id.in_([s.id for s in sessions])).order_by(WorkoutSet.session_id, WorkoutSet.id))) if sessions else []
    sets_by_session: dict[int, list[dict]] = {}
    for item in sets:
        sets_by_session.setdefault(item.session_id, []).append({"exercise": item.exercise, "set_number": item.set_number, "weight_kg": item.weight_kg, "reps": item.reps, "completed": item.completed})
    return {
        "plans": [{"id": p.id, "name": p.name, "exercises": p.exercises.splitlines()} for p in plans],
        "sessions": [{"id": s.id, "name": s.name, "started_at": s.started_at.isoformat(), "completed_at": s.completed_at.isoformat() if s.completed_at else None, "sets": sets_by_session.get(s.id, [])} for s in sessions],
    }


@app.post("/api/workouts/plans", status_code=201)
def create_workout_plan(payload: WorkoutPlanInput, user: WriteUser, db: Db):
    plan = WorkoutPlan(user_id=user.id, name=payload.name, exercises="\n".join(e.strip() for e in payload.exercises if e.strip()))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, "name": plan.name, "exercises": plan.exercises.splitlines()}


@app.post("/api/workouts/start", status_code=201)
def start_workout(payload: WorkoutStartInput, user: WriteUser, db: Db):
    if payload.plan_id:
        plan = db.scalar(select(WorkoutPlan).where(WorkoutPlan.id == payload.plan_id, WorkoutPlan.user_id == user.id))
        if not plan:
            raise HTTPException(status_code=404, detail="Workout plan not found.")
    workout = WorkoutSession(user_id=user.id, plan_id=payload.plan_id, name=payload.name)
    db.add(workout)
    db.commit()
    db.refresh(workout)
    return {"id": workout.id, "name": workout.name, "started_at": workout.started_at.isoformat()}


@app.post("/api/workouts/{session_id}/sets", status_code=201)
def add_workout_set(session_id: int, payload: SetInput, user: WriteUser, db: Db):
    workout = db.scalar(select(WorkoutSession).where(WorkoutSession.id == session_id, WorkoutSession.user_id == user.id))
    if not workout or workout.completed_at:
        raise HTTPException(status_code=404, detail="Active workout not found.")
    row = WorkoutSet(session_id=session_id, user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "exercise": row.exercise, "set_number": row.set_number, "weight_kg": row.weight_kg, "reps": row.reps, "completed": row.completed}


@app.post("/api/workouts/{session_id}/finish")
def finish_workout(session_id: int, user: WriteUser, db: Db):
    workout = db.scalar(select(WorkoutSession).where(WorkoutSession.id == session_id, WorkoutSession.user_id == user.id))
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found.")
    workout.completed_at = utc_now()
    db.commit()
    return {"id": workout.id, "completed_at": workout.completed_at.isoformat()}


@app.get("/api/body")
def body_history(user: CurrentUser, db: Db):
    rows = list(db.scalars(select(BodyMeasurement).where(BodyMeasurement.user_id == user.id).order_by(BodyMeasurement.measured_on.desc()).limit(180)))
    return [{"id": x.id, "measured_on": x.measured_on.isoformat(), "weight_kg": x.weight_kg, "waist_cm": x.waist_cm, "chest_cm": x.chest_cm, "notes": x.notes} for x in rows]


@app.post("/api/body", status_code=201)
def add_measurement(payload: MeasurementInput, user: WriteUser, db: Db):
    row = BodyMeasurement(user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    if row.weight_kg is not None:
        profile = db.get(UserProfile, user.id)
        profile.current_weight_kg = row.weight_kg
        db.commit()
    return {"id": row.id, "measured_on": row.measured_on.isoformat(), "weight_kg": row.weight_kg, "waist_cm": row.waist_cm, "chest_cm": row.chest_cm, "notes": row.notes}


@app.get("/api/habits")
def habits(user: CurrentUser, db: Db, day: date = Query(default_factory=date.today)):
    hs = list(db.scalars(select(Habit).where(Habit.user_id == user.id, Habit.active.is_(True)).order_by(Habit.id)))
    done = set(db.scalars(select(HabitCompletion.habit_id).where(HabitCompletion.user_id == user.id, HabitCompletion.completed_on == day)))
    return [{"id": h.id, "name": h.name, "category": h.category, "completed": h.id in done} for h in hs]


@app.post("/api/habits", status_code=201)
def create_habit(payload: HabitInput, user: WriteUser, db: Db):
    row = Habit(user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "category": row.category, "completed": False}


@app.put("/api/habits/{habit_id}/complete")
def toggle_habit(habit_id: int, user: WriteUser, db: Db, day: date = Query(default_factory=date.today)):
    prevent_future_day(day)
    habit = db.scalar(select(Habit).where(Habit.id == habit_id, Habit.user_id == user.id))
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found.")
    completion = db.scalar(select(HabitCompletion).where(HabitCompletion.habit_id == habit_id, HabitCompletion.user_id == user.id, HabitCompletion.completed_on == day))
    if completion:
        db.delete(completion)
        completed = False
    else:
        db.add(HabitCompletion(habit_id=habit_id, user_id=user.id, completed_on=day))
        completed = True
    db.commit()
    return {"id": habit_id, "completed": completed}


@app.get("/api/skincare")
def skincare(user: CurrentUser, db: Db, day: date = Query(default_factory=date.today)):
    routines = list(db.scalars(select(SkincareRoutine).where(SkincareRoutine.user_id == user.id, SkincareRoutine.active.is_(True))))
    completed = set(db.scalars(select(SkincareCompletion.routine_id).where(SkincareCompletion.user_id == user.id, SkincareCompletion.completed_on == day)))
    return [{"id": r.id, "name": r.name, "routine_time": r.routine_time, "steps": r.steps.splitlines(), "completed": r.id in completed} for r in routines]


@app.post("/api/skincare", status_code=201)
def create_routine(payload: RoutineInput, user: WriteUser, db: Db):
    row = SkincareRoutine(user_id=user.id, name=payload.name, routine_time=payload.routine_time, steps="\n".join(payload.steps))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "routine_time": row.routine_time, "steps": row.steps.splitlines(), "completed": False}


@app.put("/api/skincare/{routine_id}/complete")
def toggle_routine(routine_id: int, user: WriteUser, db: Db, day: date = Query(default_factory=date.today)):
    prevent_future_day(day)
    routine = db.scalar(select(SkincareRoutine).where(SkincareRoutine.id == routine_id, SkincareRoutine.user_id == user.id))
    if not routine:
        raise HTTPException(status_code=404, detail="Skincare routine not found.")
    completion = db.scalar(select(SkincareCompletion).where(SkincareCompletion.routine_id == routine_id, SkincareCompletion.user_id == user.id, SkincareCompletion.completed_on == day))
    if completion:
        db.delete(completion)
        done = False
    else:
        db.add(SkincareCompletion(routine_id=routine_id, user_id=user.id, completed_on=day))
        done = True
    db.commit()
    return {"id": routine_id, "completed": done}


@app.post("/api/water", status_code=201)
def add_water(payload: WaterInput, user: WriteUser, db: Db):
    row = WaterEntry(user_id=user.id, amount_ml=payload.amount_ml, recorded_at=payload.recorded_at or datetime.now())
    db.add(row)
    db.commit()
    return {"id": row.id, "amount_ml": row.amount_ml, "recorded_at": row.recorded_at.isoformat()}


@app.get("/api/water")
def water_history(user: CurrentUser, db: Db, day: date = Query(default_factory=date.today)):
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    rows = list(db.scalars(select(WaterEntry).where(
        WaterEntry.user_id == user.id,
        WaterEntry.recorded_at >= start,
        WaterEntry.recorded_at < end,
    ).order_by(WaterEntry.recorded_at.desc())))
    return [{"id": row.id, "amount_ml": row.amount_ml, "recorded_at": row.recorded_at.isoformat()} for row in rows]


@app.put("/api/water/{entry_id}")
def edit_water(entry_id: int, payload: WaterInput, user: WriteUser, db: Db):
    row = db.scalar(select(WaterEntry).where(WaterEntry.id == entry_id, WaterEntry.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="Water entry not found.")
    row.amount_ml = payload.amount_ml
    if payload.recorded_at:
        row.recorded_at = payload.recorded_at
    db.commit()
    return {"id": row.id, "amount_ml": row.amount_ml, "recorded_at": row.recorded_at.isoformat()}


@app.delete("/api/water/{entry_id}", status_code=204)
def delete_water(entry_id: int, user: WriteUser, db: Db):
    row = db.scalar(select(WaterEntry).where(WaterEntry.id == entry_id, WaterEntry.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="Water entry not found.")
    db.delete(row)
    db.commit()


@app.get("/api/reports/weekly")
def weekly_report(user: CurrentUser, db: Db, week_start: date | None = None):
    this_week_start = date.today() - timedelta(days=date.today().weekday())
    if week_start is None:
        week_start = this_week_start - timedelta(days=7)
    if week_start.weekday() != 0 or week_start >= this_week_start:
        raise HTTPException(status_code=422, detail="Choose a past Monday to review a completed week.")
    week_end = week_start + timedelta(days=7)
    start_dt, end_dt = datetime.combine(week_start, time.min), datetime.combine(week_end, time.min)
    entries = list(db.scalars(select(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.consumed_at >= start_dt, FoodEntry.consumed_at < end_dt)))
    per_day: dict[date, dict[str, float]] = {}
    for entry in entries:
        bucket = per_day.setdefault(entry.consumed_at.date(), {"calories": 0.0, "protein_g": 0.0})
        bucket["calories"] += entry.calories * entry.quantity
        bucket["protein_g"] += entry.protein_g * entry.quantity
    workouts = db.scalar(select(func.count(WorkoutSession.id)).where(
        WorkoutSession.user_id == user.id,
        WorkoutSession.completed_at.is_not(None),
        WorkoutSession.completed_at >= start_dt,
        WorkoutSession.completed_at < end_dt,
    )) or 0
    sleep_rows = list(db.scalars(select(SleepEntry).where(SleepEntry.user_id == user.id, SleepEntry.wake_time >= start_dt, SleepEntry.wake_time < end_dt)))
    weight_values = list(db.scalars(select(BodyMeasurement.weight_kg).where(
        BodyMeasurement.user_id == user.id,
        BodyMeasurement.weight_kg.is_not(None),
        BodyMeasurement.measured_on >= week_start,
        BodyMeasurement.measured_on < week_end,
    )))
    water = db.scalar(select(func.sum(WaterEntry.amount_ml)).where(WaterEntry.user_id == user.id, WaterEntry.recorded_at >= start_dt, WaterEntry.recorded_at < end_dt))
    habit_count = db.scalar(select(func.count(Habit.id)).where(Habit.user_id == user.id, Habit.active.is_(True))) or 0
    completions = db.scalar(select(func.count(HabitCompletion.id)).where(
        HabitCompletion.user_id == user.id,
        HabitCompletion.completed_on >= week_start,
        HabitCompletion.completed_on < week_end,
    )) or 0
    ordered_weights = list(db.scalars(select(BodyMeasurement.weight_kg).where(
        BodyMeasurement.user_id == user.id,
        BodyMeasurement.weight_kg.is_not(None),
        BodyMeasurement.measured_on >= week_start,
        BodyMeasurement.measured_on < week_end,
    ).order_by(BodyMeasurement.measured_on)))
    return {
        "week_start": week_start.isoformat(),
        "week_end": (week_end - timedelta(days=1)).isoformat(),
        "nutrition": {
            "logged_days": len(per_day),
            "average_calories": round(sum(day["calories"] for day in per_day.values()) / len(per_day), 1) if per_day else None,
            "average_protein_g": round(sum(day["protein_g"] for day in per_day.values()) / len(per_day), 1) if per_day else None,
            "message": "Averages include only days with food entries." if per_day else "No nutrition entries were logged this week.",
        },
        "workouts_completed": workouts,
        "weight": {
            "measurement_count": len(weight_values),
            "average_kg": round(sum(weight_values) / len(weight_values), 2) if weight_values else None,
            "trend_delta_kg": round(ordered_weights[-1] - ordered_weights[0], 2) if len(ordered_weights) >= 2 else None,
            "message": "A weekly trend needs at least two weigh-ins." if len(weight_values) < 2 else "Change between the first and last recorded weigh-in this week.",
        },
        "sleep": {
            "logged_nights": len(sleep_rows),
            "average_hours": round(sum((row.wake_time - row.bedtime).total_seconds() / 3600 for row in sleep_rows) / len(sleep_rows), 2) if sleep_rows else None,
        },
        "water": {"total_ml": water, "message": "No water entries were logged." if water is None else "Sum of manually logged water entries."},
        "habits": {"completed": completions, "possible": habit_count * 7, "completion_percent": round(completions / (habit_count * 7) * 100, 1) if habit_count else None},
    }


@app.post("/api/assistant/command")
def assistant_command(payload: AssistantCommandInput, user: WriteUser, db: Db):
    previous = db.scalar(select(AssistantCommand).where(
        AssistantCommand.user_id == user.id,
        AssistantCommand.command_id == payload.command_id,
    ))
    if previous:
        return json.loads(previous.response_json)
    text = payload.text.strip()
    lowered = text.casefold()
    response: dict
    if "remaining calories" in lowered or "calories left" in lowered or "protein still need" in lowered or "remaining protein" in lowered or "summarize my day" in lowered or "summary" == lowered:
        summary = dashboard(user, db, date.today())
        response = {
            "kind": "summary",
            "text": (
                f"Today: {summary['calories']} kcal and {summary['protein_g']} g protein. "
                + (f"{max(0, summary['calorie_target'] - summary['calories'])} kcal remain. " if summary["calorie_target"] is not None else "Set a calorie target to see calories remaining. ")
                + (f"{max(0, summary['protein_target_g'] - summary['protein_g'])} g protein remain." if summary["protein_target_g"] is not None else "Set a protein target to see protein remaining.")
            ),
            "data": summary,
        }
    elif re.search(r"\b(?:ate|eaten)\b", lowered):
        description = re.sub(r"^.*?\b(?:ate|eaten)\b", "", text, count=1, flags=re.IGNORECASE).strip(" .")
        parsed = parse_food_description(description, list(db.scalars(select(Food).order_by(Food.name))))
        response = {"kind": "food", "text": parsed.get("clarification") or "Please review these estimated foods and confirm before saving.", "parsed": parsed}
    else:
        water_match = re.search(r"\b(?:drank|drink|had)\s+(\d+(?:\.\d+)?)\s*(ml|milliliters?|l|liters?)\s+water\b", lowered)
        weight_match = re.search(r"\bweight\s+(?:as\s+)?(\d+(?:\.\d+)?)\s*(kg|kilograms?)\b", lowered)
        sleep_match = re.search(r"\bslept\s+for\s+(\d+(?:\.\d+)?)\s+hours?\b", lowered)
        workout_match = re.search(r"\bcompleted\s+(?:my\s+)?(.+?)\s+workout\b", lowered)
        if water_match:
            amount = float(water_match.group(1)) * (1000 if water_match.group(2).startswith("l") else 1)
            if not 1 <= amount <= 5000:
                response = {"kind": "clarification", "text": "Please log a water amount between 1 ml and 5,000 ml per entry."}
            else:
                row = WaterEntry(user_id=user.id, amount_ml=round(amount), recorded_at=datetime.now())
                db.add(row)
                db.flush()
                response = {"kind": "saved", "text": f"Saved {row.amount_ml} ml of water.", "data": {"id": row.id, "amount_ml": row.amount_ml}}
        elif weight_match:
            amount = float(weight_match.group(1))
            if not 20 < amount < 500:
                response = {"kind": "clarification", "text": "Please check the weight; accepted entries are between 20 and 500 kg."}
            else:
                row = BodyMeasurement(user_id=user.id, measured_on=date.today(), weight_kg=amount)
                db.add(row)
                db.get(UserProfile, user.id).current_weight_kg = amount
                db.flush()
                response = {"kind": "saved", "text": f"Saved your weight as {amount:g} kg.", "data": {"id": row.id, "weight_kg": amount}}
        elif sleep_match:
            hours = float(sleep_match.group(1))
            if not 0 < hours <= 24:
                response = {"kind": "clarification", "text": "Please enter a sleep duration from 0 to 24 hours."}
            else:
                wake = datetime.now()
                row = SleepEntry(user_id=user.id, bedtime=wake - timedelta(hours=hours), wake_time=wake)
                db.add(row)
                db.flush()
                response = {"kind": "saved", "text": f"Saved {hours:g} hours of sleep.", "data": {"id": row.id, "duration_hours": hours}}
        elif workout_match:
            name = workout_match.group(1).strip().title()
            now = utc_now()
            row = WorkoutSession(user_id=user.id, name=name, started_at=now, completed_at=now)
            db.add(row)
            db.flush()
            response = {"kind": "saved", "text": f"Saved your completed {name} workout.", "data": {"id": row.id}}
        else:
            response = {"kind": "clarification", "text": "I can help with food entries, water, weight, sleep, completed workouts, remaining calories/protein, or a day summary. Try a specific quantity, such as “I drank 500 ml water.”"}
    command = AssistantCommand(user_id=user.id, command_id=payload.command_id, response_json=json.dumps(response))
    db.add(command)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(select(AssistantCommand).where(
            AssistantCommand.user_id == user.id,
            AssistantCommand.command_id == payload.command_id,
        ))
        if previous:
            return json.loads(previous.response_json)
        raise
    return response


@app.post("/api/sleep", status_code=201)
def add_sleep(payload: SleepInput, user: WriteUser, db: Db):
    wake = payload.wake_time
    bedtime = payload.bedtime
    if wake <= bedtime:
        wake += timedelta(days=1)
    if wake - bedtime > timedelta(hours=24):
        raise HTTPException(status_code=422, detail="Sleep duration must be 24 hours or less.")
    if wake > datetime.now():
        raise HTTPException(status_code=422, detail="Sleep records cannot end in the future.")
    row = SleepEntry(user_id=user.id, bedtime=bedtime, wake_time=wake, quality=payload.quality, notes=payload.notes)
    db.add(row)
    db.commit()
    return {"id": row.id, "bedtime": row.bedtime.isoformat(), "wake_time": row.wake_time.isoformat(), "duration_hours": round((wake - bedtime).total_seconds() / 3600, 2), "quality": row.quality}


@app.get("/api/dashboard")
def dashboard(user: CurrentUser, db: Db, day: date = Query(default_factory=date.today)):
    profile = db.get(UserProfile, user.id)
    start, end = datetime.combine(day, time.min), datetime.combine(day + timedelta(days=1), time.min)
    entries = list(db.scalars(select(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.consumed_at >= start, FoodEntry.consumed_at < end)))
    totals = {key: round(sum(getattr(e, key) * e.quantity for e in entries), 1) for key in ("calories", "protein_g", "carbs_g", "fat_g")}
    water = db.scalar(select(func.coalesce(func.sum(WaterEntry.amount_ml), 0)).where(WaterEntry.user_id == user.id, WaterEntry.recorded_at >= start, WaterEntry.recorded_at < end))
    last_weight = db.scalar(select(BodyMeasurement.weight_kg).where(BodyMeasurement.user_id == user.id, BodyMeasurement.weight_kg.is_not(None)).order_by(BodyMeasurement.measured_on.desc()).limit(1))
    sleep = db.scalar(select(SleepEntry).where(SleepEntry.user_id == user.id, SleepEntry.wake_time >= start, SleepEntry.wake_time < end).order_by(SleepEntry.wake_time.desc()).limit(1))
    habit_count = db.scalar(select(func.count(Habit.id)).where(Habit.user_id == user.id, Habit.active.is_(True))) or 0
    habit_done = db.scalar(select(func.count(HabitCompletion.id)).where(HabitCompletion.user_id == user.id, HabitCompletion.completed_on == day)) or 0
    return {"date": day.isoformat(), "goal": profile.goal, "weight_kg": last_weight or profile.current_weight_kg, "target_weight_kg": profile.target_weight_kg, "calories": totals["calories"], "calorie_target": profile.calorie_target, "protein_g": totals["protein_g"], "protein_target_g": profile.protein_target_g, "carbs_g": totals["carbs_g"], "carbs_target_g": profile.carbs_target_g, "fat_g": totals["fat_g"], "fat_target_g": profile.fat_target_g, "water_ml": water, "water_target_ml": profile.water_target_ml, "sleep_hours": round((sleep.wake_time - sleep.bedtime).total_seconds() / 3600, 1) if sleep else None, "habits_done": habit_done, "habits_total": habit_count}


@app.get("/api/analytics/export")
def export_csv(user: CurrentUser, db: Db):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "weight_kg", "waist_cm", "calories", "protein_g"])
    rows = db.execute(select(BodyMeasurement.measured_on, BodyMeasurement.weight_kg, BodyMeasurement.waist_cm).where(BodyMeasurement.user_id == user.id).order_by(BodyMeasurement.measured_on)).all()
    measurements = {measured_on: (weight, waist) for measured_on, weight, waist in rows}
    nutrition_by_day = {}
    for entry in db.scalars(select(FoodEntry).where(FoodEntry.user_id == user.id)):
        key = entry.consumed_at.date()
        nutrition_by_day[key] = nutrition_by_day.get(key, [0, 0])
        nutrition_by_day[key][0] += entry.calories * entry.quantity
        nutrition_by_day[key][1] += entry.protein_g * entry.quantity
    for recorded_on in sorted(measurements.keys() | nutrition_by_day.keys()):
        weight, waist = measurements.get(recorded_on, (None, None))
        nutrition = nutrition_by_day.get(recorded_on)
        writer.writerow([
            recorded_on.isoformat(),
            weight if weight is not None else "",
            waist if waist is not None else "",
            round(nutrition[0], 1) if nutrition else "",
            round(nutrition[1], 1) if nutrition else "",
        ])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=aura-progress.csv"})


@app.delete("/api/account", status_code=204)
def delete_account(user: WriteUser, db: Db, response: Response):
    db.delete(user)
    db.commit()
    response.delete_cookie("aura_session", path="/")
    response.delete_cookie("aura_csrf", path="/")
