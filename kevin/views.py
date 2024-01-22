from django import http
from django.shortcuts import render


def show_web(request: http.HttpRequest):
    return render(request, "index.html")
