"""ORM model package.

Importing this package registers every SQLAlchemy model on the shared
``Base.metadata`` so that ``Base.metadata.create_all()`` (used by the test
suite and bootstrap code) sees all tables. The previous conflicting model set
under ``app.db.models.*`` has been removed, so it is now safe to import these.
"""

from app.db.base import Base

# Import each model module for its side effect of registering tables on Base.
from app.models.backtest import Backtest
from app.models.benchmark import NEPSEIndex, SectorIndex
from app.models.data_quality import (
    DataQualityAlert,
    DataQualityReport,
    DataTrust,
    EventOverride,
    HolidayCalendar,
    SourceCorrelation,
    SystemModeHistory,
)
from app.models.data_source import DataSource, IngestionLog
from app.models.dataset import Dataset
from app.models.drift_event import DriftEvent
from app.models.feature import Feature, Features
from app.models.macro import MacroObservation, MacroSeries
from app.models.model_registry import ModelRegistry
from app.models.news import NewsArticle, NewsMention, SentimentRun
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.price import Price
from app.models.quota import ProviderQuotaUsage
from app.models.signal import Signal
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.telegram import TelegramDailyAlert
from app.models.trade import Trade
from app.models.user import User

__all__ = [
    "Base",
    "Backtest",
    "NEPSEIndex",
    "SectorIndex",
    "HolidayCalendar",
    "DataTrust",
    "SourceCorrelation",
    "EventOverride",
    "DataQualityReport",
    "DataQualityAlert",
    "SystemModeHistory",
    "DataSource",
    "IngestionLog",
    "Dataset",
    "DriftEvent",
    "Feature",
    "Features",
    "MacroSeries",
    "MacroObservation",
    "ModelRegistry",
    "NewsArticle",
    "NewsMention",
    "SentimentRun",
    "PortfolioSnapshot",
    "Price",
    "ProviderQuotaUsage",
    "Signal",
    "Stock",
    "Strategy",
    "TelegramDailyAlert",
    "Trade",
    "User",
]
