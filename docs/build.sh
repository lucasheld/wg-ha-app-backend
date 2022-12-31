#!/bin/sh

BASEDIR=$(dirname $0)

asyncapi generate fromTemplate "${BASEDIR}/asyncapi.yaml" @asyncapi/html-template -o "${BASEDIR}/build"
