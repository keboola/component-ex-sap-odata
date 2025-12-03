from enum import Enum


class SnowflakeDataType(str, Enum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    NUMERIC = "NUMERIC"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    TIME = "TIME"
    TIMESTAMP = "TIMESTAMP"
    TIMESTAMP_TZ = "TIMESTAMP_TZ"


SAP_TO_SNOWFLAKE_TYPE_MAP: dict[str, SnowflakeDataType] = {
    "Edm.String": SnowflakeDataType.STRING,
    "Edm.Guid": SnowflakeDataType.STRING,
    "Edm.Int16": SnowflakeDataType.INTEGER,
    "Edm.Int32": SnowflakeDataType.INTEGER,
    "Edm.Int64": SnowflakeDataType.INTEGER,
    "Edm.Byte": SnowflakeDataType.INTEGER,
    "Edm.SByte": SnowflakeDataType.INTEGER,
    "Edm.Decimal": SnowflakeDataType.NUMERIC,
    "Edm.Double": SnowflakeDataType.FLOAT,
    "Edm.Single": SnowflakeDataType.FLOAT,
    "Edm.DateTime": SnowflakeDataType.TIMESTAMP,
    "Edm.DateTimeOffset": SnowflakeDataType.TIMESTAMP_TZ,
    "Edm.Date": SnowflakeDataType.DATE,
    "Edm.Time": SnowflakeDataType.TIME,
    "Edm.TimeOfDay": SnowflakeDataType.TIME,
    "Edm.Boolean": SnowflakeDataType.BOOLEAN,
    "Edm.Binary": SnowflakeDataType.STRING,
    "Edm.Stream": SnowflakeDataType.STRING,
    "Edm.Geography": SnowflakeDataType.STRING,
    "Edm.Geometry": SnowflakeDataType.STRING,
}


def map_edm_type_to_snowflake(edm_type: str) -> SnowflakeDataType:
    return SAP_TO_SNOWFLAKE_TYPE_MAP.get(edm_type, SnowflakeDataType.STRING)
