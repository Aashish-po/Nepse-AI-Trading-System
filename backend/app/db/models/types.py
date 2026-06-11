from sqlalchemy import JSON, BigInteger, Integer
from sqlalchemy.dialects.postgresql import JSONB

json_dict_type = JSON().with_variant(JSONB, "postgresql")
big_int_pk_type = BigInteger().with_variant(Integer, "sqlite")
