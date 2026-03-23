from __future__ import annotations

from typing import Any

from core.conversation_engine import ConversationEngine
from core.types import ActionLink, StructuredResponse, TriageResult


class ResponseEngine:
    def __init__(self, conversation_engine: ConversationEngine) -> None:
        self.conversation_engine = conversation_engine

    def build(
        self,
        triage_result: TriageResult,
        query: str,
        session_context: dict[str, Any] | None,
        resources_payload: dict[str, Any] | None,
    ) -> StructuredResponse:
        del session_context
        resources_payload = resources_payload or {}
        direct_actions = self._action_links(resources_payload.get("actions", []))
        resource_actions = self._resource_actions(resources_payload.get("resources", []))

        if triage_result.triage_class == "emergency_potential":
            actions = self._limit_actions(direct_actions, resource_actions)
            return StructuredResponse(
                title="Pode ser uma emergencia",
                message=(
                    "Pode ser uma emergencia.\n"
                    "Ligue 112 agora.\n"
                    "Se possivel, va para a urgencia mais proxima.\n"
                    "Nao espere por mais informacao."
                ),
                decision="Pode ser uma emergencia.",
                primary_action="Ligue 112 agora.",
                actions=actions,
            )

        if triage_result.triage_class == "urgent_care":
            actions = self._limit_actions(direct_actions, resource_actions)
            return StructuredResponse(
                title="Precisa de avaliacao rapida",
                message=(
                    "Isto pode precisar de avaliacao rapida.\n"
                    "Contacte o SNS 24 ou va a uma urgencia.\n"
                    "Se piorar, ligue 112."
                ),
                decision="Isto pode precisar de avaliacao rapida.",
                primary_action="Contacte o SNS 24 ou va a uma urgencia.",
                actions=actions,
            )

        if triage_result.triage_class == "practical_health":
            actions = self._limit_actions(resource_actions, direct_actions)
            primary_label = actions[0].label if actions else "abrir o recurso principal"
            secondary_label = actions[1].label if len(actions) > 1 else None
            lines = [
                "Pode resolver isto de forma pratica.",
                f"Comece por: {primary_label}.",
            ]
            if secondary_label:
                lines.append(f"Se precisar, use: {secondary_label}.")
            return StructuredResponse(
                title=self._build_practical_title(query),
                message="\n".join(lines),
                decision="Pode resolver isto de forma pratica.",
                primary_action=f"Comece por: {primary_label}.",
                actions=actions,
            )

        free_response = self.conversation_engine.free_response(query)
        message = free_response["message"]
        decision, primary_action = self._extract_conversation_focus(message)
        return StructuredResponse(
            title="Vamos organizar isto",
            message=message,
            decision=decision,
            primary_action=primary_action,
            actions=[],
            payment_prompt=free_response.get("payment_prompt"),
        )

    def _action_links(self, raw_actions: list[dict[str, Any]]) -> list[ActionLink]:
        actions: list[ActionLink] = []
        for action in raw_actions:
            if not action.get("label") or not action.get("url"):
                continue
            actions.append(
                ActionLink(
                    label=action["label"],
                    url=action["url"],
                    style=action.get("style", "secondary"),
                    phone=action.get("phone"),
                    external=action.get("external", True),
                )
            )
        return actions

    def _resource_actions(self, raw_resources: list[dict[str, Any]]) -> list[ActionLink]:
        actions: list[ActionLink] = []
        for item in raw_resources:
            if not item.get("title") or not item.get("url"):
                continue
            target_url = item["url"]
            external = not target_url.startswith("tel:")
            style = "primary" if not actions else "secondary"
            actions.append(
                ActionLink(
                    label=item["title"],
                    url=target_url,
                    style=style,
                    phone=item.get("phone"),
                    external=external,
                )
            )
        return actions

    def _limit_actions(self, preferred: list[ActionLink], fallback: list[ActionLink]) -> list[ActionLink]:
        merged: list[ActionLink] = []
        seen: set[tuple[str, str]] = set()
        for action in preferred + fallback:
            key = (action.label, action.url)
            if key in seen:
                continue
            seen.add(key)
            merged.append(action)
            if len(merged) == 2:
                break
        if merged and all(action.style != "primary" for action in merged):
            merged[0].style = "primary"
        return merged

    def _build_practical_title(self, query: str) -> str:
        normalized = (query or "").lower()
        if "medic" in normalized:
            return "Para procurar medicamento"
        if "farmac" in normalized:
            return "Para encontrar farmacia"
        if "hospital" in normalized:
            return "Para encontrar hospital"
        if "urg" in normalized:
            return "Para encontrar urgencia"
        return "Para resolver isto"

    def _extract_conversation_focus(self, message: str) -> tuple[str, str]:
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        decision = lines[0] if lines else "Vamos organizar isto."
        action = lines[-1] if lines else "Escolha um proximo passo simples."
        return decision, action
