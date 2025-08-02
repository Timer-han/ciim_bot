from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    role = Column(String(50), default='user')  # user, moderator, admin
    city = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Связи
    registrations = relationship("EventRegistration", back_populates="user")
    created_events = relationship("Event", back_populates="creator")

class Event(Base):
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    location = Column(String(255))
    city = Column(String(100), nullable=False)
    date_time = Column(DateTime, nullable=False)
    creator_id = Column(Integer, ForeignKey('users.id'))
    max_participants = Column(Integer)
    registration_required = Column(Boolean, default=True)
    registration_open = Column(Boolean, default=True)
    is_visible = Column(Boolean, default=True)
    photo_file_id = Column(String(500))  # Telegram file_id для фото
    video_file_id = Column(String(500))  # Telegram file_id для видео
    media_type = Column(String(50))      # 'photo', 'video', None
    reminder_hours = Column(Integer, default=24)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    creator = relationship("User", back_populates="created_events")
    registrations = relationship("EventRegistration", back_populates="event")

class EventRegistration(Base):
    __tablename__ = 'event_registrations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    event_id = Column(Integer, ForeignKey('events.id'))
    registered_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    user = relationship("User", back_populates="registrations")
    event = relationship("Event", back_populates="registrations")

class Question(Base):
    __tablename__ = 'questions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text)
    is_answered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime)
    
class Donation(Base):
    __tablename__ = 'donations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Integer, nullable=False)  # в копейках
    status = Column(String(50), default='pending')  # pending, completed, failed
    payment_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)