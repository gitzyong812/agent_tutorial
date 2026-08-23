[中文](./README.md) | [English](./README-en.md)

# Chapter 1 Companion Code

This directory contains the minimal large language model calling examples for Chapter 1 of *Hands-On Agent Building*. The program performs one ordinary question-answer interaction and one interaction with a role prompt, helping readers observe how a system prompt affects the response style.

## Environment Setup

Python 3.10 or later is recommended. Install the dependencies in a virtual environment:

```bash
python -m pip install -r requirements.txt
```

Copy the example environment file:

```bash
cp .env.example .env
```

Complete `.env` according to the OpenAI-compatible model service you use. Do not commit a `.env` file containing a real API key.

## Run

Run the following command in this directory:

```bash
python main.py
```

If the configuration is correct, the terminal will display the model responses to the ordinary prompt and the role prompt in sequence. See the [Chapter 1 text](../README-en.md) for detailed code explanations and exercise requirements.
