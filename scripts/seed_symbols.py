from backend.app.db.session import SessionLocal
from backend.app.models.stock import Stock

SEED_SYMBOLS = [
    {"symbol": "NABIL", "name": "Nabil Bank Limited", "sector": "Commercial Banks"},
    {"symbol": "NICA", "name": "NIC Asia Bank Limited", "sector": "Commercial Banks"},
    {"symbol": "GBIME", "name": "Global IME Bank Limited", "sector": "Commercial Banks"},
    {"symbol": "NLIC", "name": "Nepal Life Insurance Company Limited", "sector": "Life Insurance"},
    {"symbol": "UPPER", "name": "Upper Tamakoshi Hydropower Limited", "sector": "Hydropower"},
    {"symbol": "NRIC", "name": "Rastriya Beema Sansthan", "sector": "Non-Life Insurance"},
    {"symbol": "NIBLPF", "name": "NIBL Pragati Fund", "sector": "Mutual Funds"},
]


def main() -> None:
    with SessionLocal() as db:
        for item in SEED_SYMBOLS:
            stock = db.query(Stock).filter(Stock.symbol == item["symbol"]).one_or_none()
            if stock is None:
                db.add(Stock(**item))
        db.commit()
    print(f"Seeded {len(SEED_SYMBOLS)} NEPSE symbols.")


if __name__ == "__main__":
    main()
