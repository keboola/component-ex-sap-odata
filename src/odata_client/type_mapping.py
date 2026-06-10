from enum import StrEnum

from keboola.component.dao import SupportedDataTypes


class SnowflakeDataType(StrEnum):
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


# Keboola base types are the backend-agnostic types used in output table manifests
# (the `schema` / `KBC.datatype.basetype` layer). SupportedDataTypes has no dedicated
# TIME or timezone-aware TIMESTAMP, so Edm.Time* falls back to STRING and
# Edm.DateTimeOffset maps to plain TIMESTAMP.
SAP_TO_BASE_TYPE_MAP: dict[str, SupportedDataTypes] = {
    "Edm.String": SupportedDataTypes.STRING,
    "Edm.Guid": SupportedDataTypes.STRING,
    "Edm.Int16": SupportedDataTypes.INTEGER,
    "Edm.Int32": SupportedDataTypes.INTEGER,
    "Edm.Int64": SupportedDataTypes.INTEGER,
    "Edm.Byte": SupportedDataTypes.INTEGER,
    "Edm.SByte": SupportedDataTypes.INTEGER,
    "Edm.Decimal": SupportedDataTypes.NUMERIC,
    "Edm.Double": SupportedDataTypes.FLOAT,
    "Edm.Single": SupportedDataTypes.FLOAT,
    "Edm.DateTime": SupportedDataTypes.TIMESTAMP,
    "Edm.DateTimeOffset": SupportedDataTypes.TIMESTAMP,
    "Edm.Date": SupportedDataTypes.DATE,
    "Edm.Time": SupportedDataTypes.STRING,
    "Edm.TimeOfDay": SupportedDataTypes.STRING,
    "Edm.Boolean": SupportedDataTypes.BOOLEAN,
    "Edm.Binary": SupportedDataTypes.STRING,
    "Edm.Stream": SupportedDataTypes.STRING,
    "Edm.Geography": SupportedDataTypes.STRING,
    "Edm.Geometry": SupportedDataTypes.STRING,
}


def map_edm_type_to_base_type(edm_type: str | None) -> SupportedDataTypes:
    """Map an OData EDM type to a Keboola base data type for output manifests.

    Unknown or missing types (e.g. flattened/expanded nested fields without
    metadata) fall back to STRING.
    """
    if not edm_type:
        return SupportedDataTypes.STRING
    return SAP_TO_BASE_TYPE_MAP.get(edm_type, SupportedDataTypes.STRING)
