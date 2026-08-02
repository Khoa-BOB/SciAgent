#!/bin/bash
docker run -d \
  --name neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/myStrongPassword123 \
  -v neo4j_data:/data \
  neo4j:latest