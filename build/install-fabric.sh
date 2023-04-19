#!/bin/sh
MINECRAFT_VERSION=$1
FABRIC_LOADER_VERSION=$2
FABRIC_INSTALLER_VERSION=$3

curl -s -o server.jar "https://meta.fabricmc.net/v2/versions/loader/${MINECRAFT_VERSION}/${FABRIC_LOADER_VERSION}/${FABRIC_INSTALLER_VERSION}/server/jar"