FROM maven:3.9-eclipse-temurin-25 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q package -DskipTests

FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --from=build /app/target/app.jar app.jar
EXPOSE 8080
# 2 GiB konteyner limitinde heap üst sınırı ~1 GiB (MaxRAMPercentage=50). 2 CPU + 2 GiB "server-class" sayılır, G1 GC seçilir.
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=50", "-jar", "app.jar"]
