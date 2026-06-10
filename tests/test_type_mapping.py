from keboola.component.dao import SupportedDataTypes

from odata_client.type_mapping import (
    SAP_TO_SNOWFLAKE_TYPE_MAP,
    SnowflakeDataType,
    map_edm_type_to_base_type,
    map_edm_type_to_snowflake,
)


class TestTypeMapping:
    def test_string_types(self) -> None:
        assert map_edm_type_to_snowflake("Edm.String") == SnowflakeDataType.STRING
        assert map_edm_type_to_snowflake("Edm.Guid") == SnowflakeDataType.STRING

    def test_integer_types(self) -> None:
        assert map_edm_type_to_snowflake("Edm.Int16") == SnowflakeDataType.INTEGER
        assert map_edm_type_to_snowflake("Edm.Int32") == SnowflakeDataType.INTEGER
        assert map_edm_type_to_snowflake("Edm.Int64") == SnowflakeDataType.INTEGER
        assert map_edm_type_to_snowflake("Edm.Byte") == SnowflakeDataType.INTEGER
        assert map_edm_type_to_snowflake("Edm.SByte") == SnowflakeDataType.INTEGER

    def test_numeric_types(self) -> None:
        assert map_edm_type_to_snowflake("Edm.Decimal") == SnowflakeDataType.NUMERIC

    def test_float_types(self) -> None:
        assert map_edm_type_to_snowflake("Edm.Double") == SnowflakeDataType.FLOAT
        assert map_edm_type_to_snowflake("Edm.Single") == SnowflakeDataType.FLOAT

    def test_datetime_types(self) -> None:
        assert map_edm_type_to_snowflake("Edm.DateTime") == SnowflakeDataType.TIMESTAMP
        assert map_edm_type_to_snowflake("Edm.DateTimeOffset") == SnowflakeDataType.TIMESTAMP_TZ

    def test_date_time_types(self) -> None:
        assert map_edm_type_to_snowflake("Edm.Date") == SnowflakeDataType.DATE
        assert map_edm_type_to_snowflake("Edm.Time") == SnowflakeDataType.TIME
        assert map_edm_type_to_snowflake("Edm.TimeOfDay") == SnowflakeDataType.TIME

    def test_boolean_type(self) -> None:
        assert map_edm_type_to_snowflake("Edm.Boolean") == SnowflakeDataType.BOOLEAN

    def test_binary_type(self) -> None:
        assert map_edm_type_to_snowflake("Edm.Binary") == SnowflakeDataType.STRING

    def test_unknown_type_defaults_to_string(self) -> None:
        assert map_edm_type_to_snowflake("Edm.Unknown") == SnowflakeDataType.STRING
        assert map_edm_type_to_snowflake("CustomType") == SnowflakeDataType.STRING

    def test_type_map_completeness(self) -> None:
        expected_types = [
            "Edm.String",
            "Edm.Guid",
            "Edm.Int16",
            "Edm.Int32",
            "Edm.Int64",
            "Edm.Byte",
            "Edm.SByte",
            "Edm.Decimal",
            "Edm.Double",
            "Edm.Single",
            "Edm.DateTime",
            "Edm.DateTimeOffset",
            "Edm.Date",
            "Edm.Time",
            "Edm.TimeOfDay",
            "Edm.Boolean",
            "Edm.Binary",
        ]

        for edm_type in expected_types:
            assert edm_type in SAP_TO_SNOWFLAKE_TYPE_MAP, f"Missing mapping for {edm_type}"


class TestBaseTypeMapping:
    """EDM → Keboola base type mapping used for output manifest schemas."""

    def test_common_types(self) -> None:
        assert map_edm_type_to_base_type("Edm.String") == SupportedDataTypes.STRING
        assert map_edm_type_to_base_type("Edm.Int32") == SupportedDataTypes.INTEGER
        assert map_edm_type_to_base_type("Edm.Decimal") == SupportedDataTypes.NUMERIC
        assert map_edm_type_to_base_type("Edm.Double") == SupportedDataTypes.FLOAT
        assert map_edm_type_to_base_type("Edm.Boolean") == SupportedDataTypes.BOOLEAN
        assert map_edm_type_to_base_type("Edm.Date") == SupportedDataTypes.DATE
        assert map_edm_type_to_base_type("Edm.DateTime") == SupportedDataTypes.TIMESTAMP

    def test_datetimeoffset_falls_back_to_timestamp(self) -> None:
        # SupportedDataTypes has no timezone-aware variant.
        assert map_edm_type_to_base_type("Edm.DateTimeOffset") == SupportedDataTypes.TIMESTAMP

    def test_time_falls_back_to_string(self) -> None:
        # SupportedDataTypes has no TIME type.
        assert map_edm_type_to_base_type("Edm.Time") == SupportedDataTypes.STRING

    def test_unknown_and_none_default_to_string(self) -> None:
        assert map_edm_type_to_base_type("Edm.Something") == SupportedDataTypes.STRING
        assert map_edm_type_to_base_type(None) == SupportedDataTypes.STRING


class TestSnowflakeDataType:
    def test_enum_values(self) -> None:
        assert SnowflakeDataType.STRING.value == "STRING"
        assert SnowflakeDataType.INTEGER.value == "INTEGER"
        assert SnowflakeDataType.NUMERIC.value == "NUMERIC"
        assert SnowflakeDataType.FLOAT.value == "FLOAT"
        assert SnowflakeDataType.BOOLEAN.value == "BOOLEAN"
        assert SnowflakeDataType.DATE.value == "DATE"
        assert SnowflakeDataType.TIME.value == "TIME"
        assert SnowflakeDataType.TIMESTAMP.value == "TIMESTAMP"
        assert SnowflakeDataType.TIMESTAMP_TZ.value == "TIMESTAMP_TZ"
