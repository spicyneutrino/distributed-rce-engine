from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from .database import Base

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(String, primary_key = True, index = True) # UUID
    filename = Column(String)
    status = Column(String, default = "QUEUED") #QUEUED, PROCESSING, COMPLETED, FAILED
    created_at = Column(DateTime(timezone=True), server_default = func.now())
    logs = Column(Text, nullable = True) # store logs