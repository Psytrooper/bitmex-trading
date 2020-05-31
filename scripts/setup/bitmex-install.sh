#!/usr/bin/env bash

# Install python and pip.
sudo yum install python36.i686 python36-pip.noarch python36-tools.x86_64
sudo pip-3.6 install --upgrade pip

# Install mysql client.
sudo yum install mysql57.x86_64

exit 0
