from json import JSONDecodeError, load
from logging import INFO, getLogger
from typing import Any

from pydantic import ValidationError

from app.models import IngoingMessage, OutgoingMessage, RuleObject, RuleOptions
from app.types import Handler, Platform

logger = getLogger("Message Router")
logger.setLevel(INFO)
counter = 0


def format_message(message: IngoingMessage, options: RuleOptions) -> str:
    if not options.message_mark:
        return message["content"]

    content = message["content"]
    content += "\n"

    for mark_item in options.message_mark:
        match mark_item:
            case "user_id":
                content += f"\nUSER_ID: {message['user_id']}"
            case "user_name":
                user_name = message.get("user_name")
                if user_name is None:
                    logger.warning(
                        f"user_name is required by rule but not set in IngoingMessage object {message}"
                    )
                else:
                    content += f"\nBY: {user_name}"
            case "chat_id":
                content += f"\nCHAT_ID: {message['chat_id']}"
            case "chat_name":
                chat_name = message.get("chat_name")
                if chat_name is None:
                    logger.warning(
                        f"chat_name is required by rule but not set in IngoingMessage object {message}",
                    )
                else:
                    content += f"\nCHAT_NAME: {chat_name}"
            case "datemark":
                send_at = message["timestamp"].strftime(options.datemark_format)
                content += f"\nAT: {send_at}"
            case "platform":
                content += f"\nPLATFORM: {message['platform']}"

    return content


def match_rule(message: IngoingMessage, rule: RuleObject) -> list[OutgoingMessage]:
    matched = False

    for from_rule in rule.from_rules:
        matched = matched or from_rule.match(message)

    if not matched:
        return []

    result: list[OutgoingMessage] = []
    content = (
        format_message(message, rule.options) if rule.options else message["content"]
    )

    for to_rule in rule.to_rules:
        result.append(
            OutgoingMessage(
                content=content, platform=to_rule.platform, chat_id=to_rule.chat_id
            )
        )

    return result


class MessageRouter:
    rules: list[RuleObject] | None
    handlers: dict[Platform, Handler]

    def __init__(self):
        self.rules = None
        self.handlers = {}

    def load_rules(self):
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
        logger.info(f"loaded {len(self.rules)} routing rules")

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

        logger.info(f"Routed message#{counter} {message} to {len(messages)} chats")
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
