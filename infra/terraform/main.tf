terraform {
  required_version = ">= 1.6.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {}

resource "docker_network" "anomalyguard" {
  name = "anomalyguard-net"
}

resource "docker_container" "postgres" {
  name  = "tf-anomalyguard-db"
  image = "timescale/timescaledb:latest-pg16"
  env = [
    "POSTGRES_DB=anomalyguard",
    "POSTGRES_USER=anomaly",
    "POSTGRES_PASSWORD=anomaly"
  ]
  ports {
    internal = 5432
    external = 5432
  }
  networks_advanced {
    name = docker_network.anomalyguard.name
  }
}

resource "docker_container" "redis" {
  name  = "tf-anomalyguard-redis"
  image = "redis:7"
  ports {
    internal = 6379
    external = 6379
  }
  networks_advanced {
    name = docker_network.anomalyguard.name
  }
}
