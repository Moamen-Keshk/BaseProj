from sqlalchemy import Column, Integer, String, ForeignKey, Date, Float, Boolean, DateTime
from sqlalchemy.orm import relationship
from app import db
import datetime

class OTARoomMapping(db):
    __tablename__ = 'ota_room_mapping'
    id = Column(Integer, primary_key=True)
    ota_name = Column(String)  # 'booking.com'
    ota_room_id = Column(String)
    local_room_id = Column(Integer, ForeignKey('rooms.id'))
    property_id = Column(Integer, ForeignKey('properties.id'))
    active = Column(Boolean, default=True)

class OTARateMapping(db):
    __tablename__ = 'ota_rate_mapping'
    id = Column(Integer, primary_key=True)
    ota_name = Column(String)
    ota_rate_plan_id = Column(String)
    local_rate_plan_id = Column(Integer, ForeignKey('rate_plans.id'))
    property_id = Column(Integer, ForeignKey('properties.id'))
    active = Column(Boolean, default=True)

class OTASyncLog(db):
    __tablename__ = 'ota_sync_log'
    id = Column(Integer, primary_key=True)
    ota_name = Column(String)
    sync_type = Column(String)  # 'rate', 'availability', 'booking'
    status = Column(String)
    message = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
