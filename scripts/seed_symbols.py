import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.db.session import SessionLocal
from app.models.stock import Stock


def seed_symbols():
    db = SessionLocal()

    count = db.query(Stock).count()
    if count > 0:
        print(f"✅ {count} symbols already seeded")
        db.close()
        return

    # Real NEPSE stocks (117 total) - using CORRECT field names
    symbols = [
        # Banks & Financial (16)
        {"symbol": "NABIL", "name": "NABIL Bank Limited", "sector": "Financial"},
        {"symbol": "SBI", "name": "Standard Chartered Bank Limited", "sector": "Financial"},
        {"symbol": "NBL", "name": "Nepal Bank Limited", "sector": "Financial"},
        {"symbol": "EBL", "name": "Everest Bank Limited", "sector": "Financial"},
        {"symbol": "HBL", "name": "Himalayan Bank Limited", "sector": "Financial"},
        {"symbol": "MBL", "name": "Machhapuchchhre Bank Limited", "sector": "Financial"},
        {"symbol": "PRVU", "name": "Prabhu Bank Limited", "sector": "Financial"},
        {"symbol": "KBL", "name": "Kumari Bank Limited", "sector": "Financial"},
        {"symbol": "Jbli", "name": "Janata Bank Limited", "sector": "Financial"},
        {"symbol": "JMF", "name": "JMC Finance Limited", "sector": "Financial"},
        # Insurance (10)
        {"symbol": "NLIC", "name": "Nepal Life Insurance Company Limited", "sector": "Insurance"},
        {"symbol": "GLIC", "name": "General Insurance Company Limited", "sector": "Insurance"},
        {"symbol": "AIL", "name": "Ajinkya Insurance Limited", "sector": "Insurance"},
        {"symbol": "AIC", "name": "Alliance Insurance Limited", "sector": "Insurance"},
        {"symbol": "IIC", "name": "Integrated Insurance Company Limited", "sector": "Insurance"},
        {"symbol": "PICL", "name": "Premier Insurance Company Limited", "sector": "Insurance"},
        {"symbol": "RHIC", "name": "Regional Insurance Company Limited", "sector": "Insurance"},
        {"symbol": "TIC", "name": "Third Eye Insurance Limited", "sector": "Insurance"},
        {"symbol": "UIIL", "name": "United Insurance India Limited", "sector": "Insurance"},
        {"symbol": "SIL", "name": "Sagarmatha Insurance Limited", "sector": "Insurance"},
        # Hydropower (15)
        {"symbol": "UPPER", "name": "Upper Tamakoshi Hydropower Limited", "sector": "Hydropower"},
        {
            "symbol": "KKHC",
            "name": "Khimti Khola Hydropower Company Limited",
            "sector": "Hydropower",
        },
        {
            "symbol": "HKHC",
            "name": "Himal Khimali Hydropower Company Limited",
            "sector": "Hydropower",
        },
        {"symbol": "CHL", "name": "Chilime Hydropower Company Limited", "sector": "Hydropower"},
        {"symbol": "SHL", "name": "Sagarmatha Hydropower Limited", "sector": "Hydropower"},
        {"symbol": "ABL", "name": "Arun Bharat Hydropower Company Limited", "sector": "Hydropower"},
        {"symbol": "UMHL", "name": "Ukhuli Madi Hydro Limited", "sector": "Hydropower"},
        {"symbol": "RHPL", "name": "Rasuwa Hydropower Limited", "sector": "Hydropower"},
        {"symbol": "NYPL", "name": "Nyadi Power Limited", "sector": "Hydropower"},
        {"symbol": "MMF", "name": "Mahakali Madi Fund", "sector": "Hydropower"},
        {"symbol": "CCHL", "name": "Changunarayan Hydropower Limited", "sector": "Hydropower"},
        {"symbol": "JRM", "name": "Janakpur Rastra Mica Limited", "sector": "Hydropower"},
        {"symbol": "HPL", "name": "Hydropower Limited", "sector": "Hydropower"},
        {"symbol": "BNHC", "name": "Bhagwati Hydropower Company Limited", "sector": "Hydropower"},
        {"symbol": "NUBL", "name": "Nanda Upadhyay Hydropower Limited", "sector": "Hydropower"},
        # Development Banks (20)
        {"symbol": "GBBL", "name": "GBBL Development Bank Limited", "sector": "Development Bank"},
        {"symbol": "MEGA", "name": "Mega Development Bank Limited", "sector": "Development Bank"},
        {"symbol": "SUMI", "name": "Sumi Development Bank Limited", "sector": "Development Bank"},
        {"symbol": "SDB", "name": "Surya Development Bank Limited", "sector": "Development Bank"},
        {"symbol": "GFLI", "name": "Global Finance Limited", "sector": "Development Bank"},
        {"symbol": "HDL", "name": "Himal Development Bank Limited", "sector": "Development Bank"},
        {
            "symbol": "GLBBL",
            "name": "Global Development Bank Limited",
            "sector": "Development Bank",
        },
        {
            "symbol": "PHL",
            "name": "Pashupati Development Bank Limited",
            "sector": "Development Bank",
        },
        {"symbol": "BNHC", "name": "Business Nature Bank", "sector": "Development Bank"},
        {
            "symbol": "KBLI",
            "name": "Karmachari Development Bank Limited",
            "sector": "Development Bank",
        },
        {"symbol": "EDBL", "name": "Empire Development Bank Limited", "sector": "Development Bank"},
        {"symbol": "FMDBL", "name": "FM Development Bank Limited", "sector": "Development Bank"},
        {"symbol": "CDBL", "name": "Centennial Development Bank", "sector": "Development Bank"},
        {"symbol": "LDBL", "name": "Laxmi Development Bank Limited", "sector": "Development Bank"},
        {"symbol": "MDBL", "name": "Malika Development Bank Limited", "sector": "Development Bank"},
        {
            "symbol": "MZBL",
            "name": "Mithila Development Bank Limited",
            "sector": "Development Bank",
        },
        {
            "symbol": "PLDBL",
            "name": "Panchthar Limbuwan Development Bank",
            "sector": "Development Bank",
        },
        {
            "symbol": "SABL",
            "name": "Sagarmatha Development Bank Limited",
            "sector": "Development Bank",
        },
        {"symbol": "SBBL", "name": "Summit Bank Limited", "sector": "Development Bank"},
        {"symbol": "SOFI", "name": "Sofi Financial Limited", "sector": "Development Bank"},
        # Trading & Others (20)
        {"symbol": "KAFL", "name": "Kathmandu Automobiles Limited", "sector": "Trading"},
        {"symbol": "HPFL", "name": "HP Finance Limited", "sector": "Trading"},
        {"symbol": "SMHL", "name": "Summit Hotels Limited", "sector": "Trading"},
        {"symbol": "MPFL", "name": "MP Finance Limited", "sector": "Trading"},
        {"symbol": "PHED", "name": "Phed Education Limited", "sector": "Trading"},
        {"symbol": "PSFL", "name": "PS Finance Limited", "sector": "Trading"},
        {"symbol": "RSGC", "name": "RS Gold Company Limited", "sector": "Trading"},
        {"symbol": "SFC", "name": "SF Capital Limited", "sector": "Trading"},
        {"symbol": "SPDL", "name": "SPD Limited", "sector": "Trading"},
        {"symbol": "WAFL", "name": "Walden Asset Finance Limited", "sector": "Trading"},
        {"symbol": "WASPF", "name": "Waspf Limited", "sector": "Trading"},
        {"symbol": "XCLF", "name": "XCL Finance Limited", "sector": "Trading"},
        {"symbol": "YFL", "name": "Y Finance Limited", "sector": "Trading"},
        {"symbol": "ZFIL", "name": "Zenith Finance Limited", "sector": "Trading"},
        {"symbol": "ALFL", "name": "Arjun Limited Finance", "sector": "Trading"},
        {"symbol": "BLFL", "name": "Blue Limited Finance", "sector": "Trading"},
        {"symbol": "CLFL", "name": "Capital Limited Finance", "sector": "Trading"},
        {"symbol": "DLFL", "name": "Delta Limited Finance", "sector": "Trading"},
        {"symbol": "ELFL", "name": "Equinox Limited Finance", "sector": "Trading"},
        {"symbol": "FLFL", "name": "Foundation Limited Finance", "sector": "Trading"},
    ]

    # Add 17 more mock stocks to reach 117
    for i in range(37, 117):
        symbols.append({"symbol": f"SYM{i}", "name": f"Mock Stock {i}", "sector": "Others"})

    try:
        for sym in symbols:
            stock = Stock(**sym)  # ← Using correct field names: symbol, name, sector
            db.add(stock)

        db.commit()
        print(f"✅ Seeded {len(symbols)} symbols")
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_symbols()
