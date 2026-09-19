from json import JSONDecodeError, load
from logging import DEBUG, getLogger
from time import time
from typing import Any

from pydantic import ValidationError

from app.models import IngoingMessage, OutgoingMessage, RuleObject, RuleOptions
from app.types import Handler, Platform

logger = getLogger("Message Router")
logger.setLevel(DEBUG)
counter = 0


def format_message(message: IngoingMessage, options: RuleOptions) -> tuple[str, str]:
    if not options.message_mark:
        return message["content"], ""

    content = message["content"]
    mark = ""

    for mark_item in options.message_mark:
        match mark_item:
            case "user_id":
                user_id = message.get("user_id")
                if user_id is None:
                    logger.warning(
                        f"user_id is required by rule but not set in IngoingMessage object {message}"
                    )
                mark += f"USER_ID: {user_id}\n"
            case "user_name":
                user_name = message.get("user_name")
                if user_name is None:
                    logger.warning(
                        f"user_name is required by rule but not set in IngoingMessage object {message}"
                    )
                else:
                    mark += f"BY: {user_name}\n"
            case "chat_id":
                mark += f"CHAT_ID: {message['chat_id']}\n"
            case "chat_name":
                chat_name = message.get("chat_name")
                if chat_name is None:
                    logger.warning(
                        f"chat_name is required by rule but not set in IngoingMessage object {message}",
                    )
                else:
                    mark += f"CHAT_NAME: {chat_name}\n"
            case "datemark":
                send_at = message["timestamp"].strftime(options.datemark_format)
                mark += f"AT: {send_at}\n"
            case "platform":
                mark += f"PLATFORM: {message['platform']}\n"
    mark = mark.removesuffix("\n")

    return content, mark


def match_rule(message: IngoingMessage, rule: RuleObject) -> list[OutgoingMessage]:
    matched = False

    for from_rule in rule.from_rules:
        matched = matched or from_rule.match(message)

    if not matched:
        return []

    result: list[OutgoingMessage] = []
    content, mark = (
        format_message(message, rule.options)
        if rule.options
        else (message["content"], "")
    )

    for to_rule in rule.to_rules:
        new_message = OutgoingMessage(
            content=content,
            mark=mark,
            platform=to_rule.platform,
            chat_id=to_rule.chat_id,
            text_content_style=None,
        )

        if rule.options:
            new_message["text_content_style"] = rule.options.text_content_style

        result.append(new_message)

    return result


class MessageRouter:
    rules: list[RuleObject] | None
    handlers: dict[Platform, Handler]

    def __init__(self):
        self.rules = None
        self.handlers = {}

    def load_rules(self) -> float:
        otime = time()
        self._load_rules()
        took = time() - otime

        if self.rules:
            logger.info(
                f"reloading rules took {took:.4f}s. loaded {len(self.rules)} rules"
            )
            return took

        logger.info(
            f"loading rules took {took:.4f}s. loaded {len(self.rules or [])} rules"
        )
        return took

    def _load_rules(self):
        with open("rules.json", "r") as file:
            try:
                json: list[dict[str, Any]] | dict[str, Any] = load(file)

                if not isinstance(json, list):
                    raise ValueError("Config root must be list")  # noqa

                rules = list(map(RuleObject.model_validate, json))
                self.rules = rules
            except ValidationError as err:
                raise ValueError(f"Config is invalid: {err.errors()}")

            except JSONDecodeError as err:
                raise ValueError(f"Config must be valid json file: {err}")

    def get_rules(self) -> list[RuleObject]:
        if self.rules is None:
            raise RuntimeError("Rules is not loaded")
        return self.rules

    def route_message(self, message: IngoingMessage) -> list[OutgoingMessage]:
        global counter

        messages: list[OutgoingMessage] = []

        rules = self.get_rules()
        for rule in rules:
            messages.extend(match_rule(message, rule))

        if logger.level == DEBUG:
            logger.debug(f"Routed message#{counter} {message} to {len(messages)} chats")
        else:
            logger.info(f"Routed message#{counter} to {len(messages)} chats")
        counter += 1

        return messages

    def register_handler(self, platform: Platform, handler: Handler):
        if platform in self.handlers:
            raise ValueError(
                f"Overwriting existing handler object {self.handlers[platform]}"
            )
        self.handlers[platform] = handler

    async def handle_message(self, ingoing_message: IngoingMessage):
        messages = self.route_message(ingoing_message)

        async def default_handler(message: OutgoingMessage):
            logger.error(f"no handler for platform: {message['platform']}")

        for message in messages:
            handler = self.handlers.get(message["platform"], default_handler)
            try:
                await handler(message)
            except Exception:
                logger.exception(
                    f"Exception during sending to {message['platform']}: {message}"
                )


message_router = MessageRouter()
