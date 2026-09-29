# Phase 5 — Debezium Connect + Confluent's Avro converter, so CDC topics get the same
# Schema-Registry-backed Avro encoding as the behavioral topics (§41 reads as a project-wide
# encoding rule, not scoped to just behavioral events). The base image doesn't bundle a
# Confluent-licensed converter, so it's installed directly here (curl+unzip, confirmed present
# in the base image) rather than depending on the confluent-hub CLI being available.
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
