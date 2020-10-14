import logging
from pathlib import Path

from celery.schedules import crontab
from flask import Flask
from flask.logging import default_handler

from datalad_registry import celery
from datalad_registry import dataset_urls
from datalad_registry.models import db
from datalad_registry.models import init_db_command


def _setup_logging(level):
    lgr = logging.getLogger("datalad_registry")
    lgr.setLevel(level)
    lgr.addHandler(default_handler)


def setup_celery(app, celery):
    celery.conf.beat_schedule = {
        "prune_old_tokens": {
            "task": "datalad_registry.tasks.prune_old_tokens",
            "schedule": crontab(hour=4, minute=0)},
    }
    celery.config_from_object(app.config, namespace="CELERY")

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


def create_app(test_config=None):
    app = Flask(__name__)
    instance_path = Path(app.instance_path)
    db_uri = "sqlite:///" + str(instance_path / "registry.sqlite")
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False)

    if app.config["ENV"] == "production" and not test_config:
        raise RuntimeError("Not ready yet")
    else:
        config_obj = "datalad_registry.config.DevelopmentConfig"
    app.config.from_object(config_obj)

    app.config.from_envvar("DATALAD_REGISTRY_CONFIG", silent=True)
    if test_config:
        app.config.from_mapping(test_config)

    _setup_logging(app.config["DATALAD_REGISTRY_LOG_LEVEL"])

    instance_path.mkdir(parents=True, exist_ok=True)
    setup_celery(app, celery)
    db.init_app(app)
    app.cli.add_command(init_db_command)
    app.register_blueprint(dataset_urls.bp)
    return app
