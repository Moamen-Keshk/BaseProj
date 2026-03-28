from threading import Thread
from typing import Any, cast

from flask import current_app, render_template
from flask.app import Flask
from flask_mail import Message

from app import mail


def send_async_email(app: Flask, msg: Message) -> None:
    with app.app_context():
        mail.send(msg)


def send_email(to: str, subject: str, template: str, **kwargs: Any) -> Thread:
    app = cast(Flask, current_app._get_current_object())

    msg = Message(
        subject=f"{app.config['FLASKY_MAIL_SUBJECT_PREFIX']} {subject}",
        sender=app.config["FLASKY_MAIL_SENDER"],
        recipients=[to],
    )
    msg.body = render_template(f"{template}.txt", **kwargs)
    msg.html = render_template(f"{template}.html", **kwargs)

    thr = Thread(target=send_async_email, args=(app, msg), daemon=True)
    thr.start()
    return thr