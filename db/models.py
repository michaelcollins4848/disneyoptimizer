from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Float
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

#represents a park, but currently only working on just disneyland
class Park(Base):
    __tablename__ = "parks"

    id = Column(String, primary_key=True)   # themeparks.wiki entity ID
    name = Column(String, nullable=False)
    timezone = Column(String, nullable=False)
    rides = relationship("Ride", back_populates="park")


class Ride(Base):
    __tablename__ = "rides"

    id = Column(String, primary_key=True)  # themeparks.wiki entity ID
    park_id = Column(String, ForeignKey("parks.id"), nullable=False)
    name = Column(String, nullable=False)
    entity_type = Column(String) # ATTRACTION, SHOW, etc.
    duration_minutes = Column(Integer, nullable=True)
    latitude         = Column(Float, nullable=True)
    longitude        = Column(Float, nullable=True) 
    park = relationship("Park", back_populates="rides")

    snapshots = relationship("WaitTimeSnapshot", back_populates="ride")

#single wait time reading for one ride at one point in time.

class WaitTimeSnapshot(Base):
    __tablename__ = "wait_time_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ride_id = Column(String, ForeignKey("rides.id"), nullable=False)
    wait_minutes = Column(Integer, nullable=True)   # null if ride is closed/down
    status = Column(String) # OPERATING, DOWN, CLOSED, REFURBISHMENT

    #when the reading was taken
    recorded_at  = Column(DateTime(timezone=True), nullable=False)

    #pre-computed time features for ML (derived from recorded_at)
    hour_of_day = Column(Integer)   # 0–23
    day_of_week = Column(Integer)   # 0=Mon … 6=Sun
    month = Column(Integer)   # 1–12
    is_weekend = Column(Boolean)
    is_holiday = Column(Boolean)

    ride = relationship("Ride", back_populates="snapshots")

#any form of live entertainment (fireworks, parades, etc.)
class Show(Base):
    __tablename__ = "shows"

    id = Column(String, primary_key=True)
    park_id = Column(String, ForeignKey("parks.id"), nullable=False)
    name = Column(String, nullable=False)

    showtimes = relationship("ShowTime", back_populates="show")


class ShowTime(Base):
    __tablename__ = "show_times"

    id = Column(Integer, primary_key=True, autoincrement=True)
    show_id = Column(String, ForeignKey("shows.id"), nullable=False)
    show_date = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)

    show = relationship("Show", back_populates="showtimes")