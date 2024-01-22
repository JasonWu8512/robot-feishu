#! /usr/bin/env bash

gunicorn kevin.wsgi -c gunicorn_config.py
