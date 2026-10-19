ARG BASE_IMAGE=domain-admin-base:latest
FROM ${BASE_IMAGE}

COPY . /app

CMD ["gunicorn", "--bind", "[::]:8000", "--timeout", "120", "domain_admin.main:app"]
