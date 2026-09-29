# Same as debezium/Dockerfile — duplicated here rather than shared since this compose file
# builds it with a different relative context (the VM deployment bundles kafka+schema-registry+
# connect into one compose project instead of the local dev split across kafka/ and debezium/).
FROM debezium/connect:2.7.3.Final

ARG AVRO_CONVERTER_VERSION=7.6.1

RUN curl -sSL \
      "https://hub-downloads.confluent.io/api/plugins/confluentinc/kafka-connect-avro-converter/versions/${AVRO_CONVERTER_VERSION}/confluentinc-kafka-connect-avro-converter-${AVRO_CONVERTER_VERSION}.zip" \
      -o /tmp/avro-converter.zip \
    && mkdir -p /tmp/avro-converter \
    && unzip -q /tmp/avro-converter.zip -d /tmp/avro-converter \
    && mkdir -p /kafka/connect/kafka-connect-avro-converter \
    && cp /tmp/avro-converter/confluentinc-kafka-connect-avro-converter-${AVRO_CONVERTER_VERSION}/lib/*.jar /kafka/connect/kafka-connect-avro-converter/ \
    && rm -rf /tmp/avro-converter /tmp/avro-converter.zip
