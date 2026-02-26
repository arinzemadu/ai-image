import datetime
from sqlalchemy import Column, Integer, String, DateTime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True) # Nullable because Google users don't have one
    
    stripe_customer_id = Column(String, unique=True, index=True, nullable=True)
    subscription_plan = Column(String, default="free", nullable=False)
    monthly_usage_count = Column(Integer, default=0, nullable=False)
    usage_reset_date = Column(DateTime, default=datetime.datetime.utcnow() + datetime.timedelta(days=30), nullable=False)
