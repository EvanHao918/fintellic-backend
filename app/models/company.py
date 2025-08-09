# app/models/company.py
"""
Company model - Represents companies tracked in the system
ENHANCED: Added IPO support, better categorization, and more company metadata
FIXED: Added update_filings_ticker method to fix edgar_scanner error
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Session
from datetime import datetime
from app.models.base import Base


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = {'extend_existing': True}  # 添加这行以防万一
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # SEC identifiers
    cik = Column(String(10), unique=True, index=True, nullable=False)  # Central Index Key
    ticker = Column(String(10), unique=True, index=True, nullable=True)  # 改为可空，支持IPO
    
    # Company information
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255))
    
    # Classification - 增强分类信息
    sic = Column(String(10))  # Standard Industrial Classification
    sic_description = Column(String(255))
    sector = Column(String(100))  # 新增：标准行业板块
    industry = Column(String(100))  # 新增：细分行业
    
    # Location
    state = Column(String(2))
    state_of_incorporation = Column(String(2))
    headquarters = Column(String(100))  # 新增：总部城市
    country = Column(String(50), default="United States")  # 新增：国家
    
    # Business details
    fiscal_year_end = Column(String(4))  # MMDD format
    business_address = Column(Text)
    mailing_address = Column(Text)
    founded_year = Column(Integer)  # 新增：成立年份
    employees = Column(Integer)  # 新增：员工数量
    
    # Financial metrics (可选，用于成熟公司)
    market_cap = Column(Float)  # 市值（百万美元）
    
    # Contact
    business_phone = Column(String(50))
    website = Column(String(255))  # 新增：公司网站
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=True, nullable=False)  # 新增：是否上市
    
    # Market info
    exchange = Column(String(50))
    is_sp500 = Column(Boolean, default=False, nullable=False)
    is_nasdaq100 = Column(Boolean, default=False, nullable=False)
    
    # IPO specific
    has_s1_filing = Column(Boolean, default=False, nullable=False)  # 新增：是否有S-1文件
    ipo_date = Column(DateTime(timezone=True))  # 新增：IPO日期
    
    # Index membership (e.g., "S&P 500,NASDAQ 100")
    indices = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_filing_date = Column(DateTime(timezone=True))
    
    # Relationships
    filings = relationship("Filing", back_populates="company")
    earnings_calendar = relationship("EarningsCalendar", back_populates="company")
    watchers = relationship("Watchlist", back_populates="company", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Company(id={self.id}, ticker='{self.ticker}', name='{self.name}')>"
    
    @property
    def display_ticker(self):
        """显示用的ticker，IPO公司可能没有"""
        return self.ticker or f"IPO-{self.cik[-4:]}"
    
    @property
    def index_list(self):
        """Return indices as a list"""
        if not self.indices:
            return []
        return [idx.strip() for idx in self.indices.split(',')]
    
    @property
    def is_watchable(self):
        """Check if company is in S&P 500 or NASDAQ 100"""
        return self.is_sp500 or self.is_nasdaq100
    
    @property
    def indices_list(self):
        """Get list of indices this company belongs to (for API response)"""
        indices = []
        if self.is_sp500:
            indices.append("S&P 500")
        if self.is_nasdaq100:
            indices.append("NASDAQ 100")
        if self.has_s1_filing and not self.is_public:
            indices.append("IPO Candidate")
        return indices
    
    @property
    def company_type(self):
        """获取公司类型描述"""
        if self.has_s1_filing and not self.is_public:
            return "Pre-IPO"
        elif self.is_sp500 or self.is_nasdaq100:
            return "Large Cap"
        else:
            return "Public Company"
    
    @property
    def employee_size_category(self):
        """获取员工规模分类"""
        if not self.employees:
            return None
        elif self.employees < 100:
            return "Small (<100)"
        elif self.employees < 1000:
            return "Medium (100-1K)"
        elif self.employees < 10000:
            return "Large (1K-10K)"
        else:
            return "Enterprise (10K+)"
    
    def update_indices(self):
        """Update indices field based on boolean flags"""
        indices = []
        if self.is_sp500:
            indices.append("S&P 500")
        if self.is_nasdaq100:
            indices.append("NASDAQ 100")
        self.indices = ",".join(indices) if indices else None
    
    # ==================== FIXED: 添加缺失的方法 ====================
    def update_filings_ticker(self, db: Session = None):
        """
        Update ticker for all filings of this company
        FIXED: Added this method to resolve edgar_scanner error
        
        Args:
            db: Optional database session for updating filings
        """
        # Update last filing date
        self.last_filing_date = datetime.utcnow()
        
        # If we have a database session and ticker, update filings
        if db and self.ticker:
            # Import here to avoid circular import
            from app.models.filing import Filing
            
            # Update all filings for this company that don't have ticker
            filings_without_ticker = db.query(Filing).filter(
                Filing.company_id == self.id,
                (Filing.ticker == None) | (Filing.ticker == '')
            ).all()
            
            for filing in filings_without_ticker:
                filing.ticker = self.ticker
            
            # Note: Don't commit here, let the caller handle transaction
    # ================================================================
    
    def to_dict_basic(self):
        """返回基础信息字典（用于S-1等数据不全的情况）"""
        return {
            "id": self.id,
            "cik": self.cik,
            "ticker": self.display_ticker,
            "name": self.name,
            "is_public": self.is_public,
            "has_s1_filing": self.has_s1_filing
        }
    
    def to_dict_full(self):
        """返回完整信息字典（用于成熟公司）"""
        return {
            "id": self.id,
            "cik": self.cik,
            "ticker": self.ticker,
            "name": self.name,
            "legal_name": self.legal_name,
            "sector": self.sector,
            "industry": self.industry,
            "headquarters": self.headquarters,
            "country": self.country,
            "founded_year": self.founded_year,
            "employees": self.employees,
            "employee_size": self.employee_size_category,
            "market_cap": self.market_cap,
            "exchange": self.exchange,
            "is_sp500": self.is_sp500,
            "is_nasdaq100": self.is_nasdaq100,
            "indices": self.indices_list,
            "company_type": self.company_type,
            "website": self.website,
            "fiscal_year_end": self.fiscal_year_end,
            "state": self.state,
            "is_public": self.is_public,
            "has_s1_filing": self.has_s1_filing,
            "ipo_date": self.ipo_date.isoformat() if self.ipo_date else None
        }