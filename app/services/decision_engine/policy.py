"""
Gestor de Resoluciones de Política Jerárquica e Inmutable (EduAgro).
Combina capas con orden de precedencia estricto y conserva la procedencia exacta de cada valor.
"""

from typing import Dict, Any, List, Optional, Union
from uuid import UUID

from app.services.decision_engine.models import EffectivePolicyValue, DecisionPolicy
from app.services.decision_engine.policy_defaults import SYSTEM_BASE_DECISION_POLICY


SCOPE_PRIORITY = [
    "system_base",
    "agronomic_template",
    "organization",
    "family_client",
    "field",
    "lot",
    "run_override",
]


class PolicyLayer:
    def __init__(
        self,
        scope: str,
        policy_data: Dict[str, Any],
        source_id: Optional[Union[UUID, str]] = None,
        policy_id: Optional[str] = None,
        policy_version: Optional[str] = None,
    ):
        if scope not in SCOPE_PRIORITY:
            raise ValueError(f"Scope no válido: '{scope}'. Debe ser uno de {SCOPE_PRIORITY}")
        self.scope = scope
        self.policy_data = policy_data
        self.source_id = source_id
        self.policy_id = policy_id
        self.policy_version = policy_version


class DecisionPolicyResolver:
    """
    Resuelve determinísticamente la política efectiva combinando capas según su jerarquía.
    """

    def __init__(self, layers: Optional[List[PolicyLayer]] = None):
        base_layer = PolicyLayer(
            scope="system_base",
            policy_data=SYSTEM_BASE_DECISION_POLICY,
            policy_id="system-base",
            policy_version="2.0.0",
        )
        self.layers: List[PolicyLayer] = [base_layer]

        if layers:
            # Ordenar capas según jerarquía de precedencia
            sorted_layers = sorted(layers, key=lambda l: SCOPE_PRIORITY.index(l.scope))
            for layer in sorted_layers:
                if layer.scope != "system_base":
                    self.layers.append(layer)

    def resolve(self) -> Dict[str, EffectivePolicyValue]:
        """
        Retorna un mapa aplanado de clave de política -> EffectivePolicyValue.
        """
        effective_map: Dict[str, EffectivePolicyValue] = {}

        for layer in self.layers:
            self._flatten_and_merge(
                data=layer.policy_data,
                prefix="",
                layer=layer,
                target_map=effective_map,
            )

        # Protección estricta de controles de seguridad (Safety Controls)
        base_allow_override = SYSTEM_BASE_DECISION_POLICY.get("safety", {}).get("allow_override_safety_controls", False)

        if not base_allow_override:
            base_safety_req = SYSTEM_BASE_DECISION_POLICY.get("safety", {}).get(
                "require_data_quality_for_positive_recommendation", True
            )
            effective_map["safety.require_data_quality_for_positive_recommendation"] = EffectivePolicyValue(
                value=base_safety_req,
                source_scope="system_base",
                policy_id="system-base",
                policy_version="2.0.0",
            )
            effective_map["safety.allow_override_safety_controls"] = EffectivePolicyValue(
                value=False,
                source_scope="system_base",
                policy_id="system-base",
                policy_version="2.0.0",
            )

        return effective_map

    def _flatten_and_merge(
        self,
        data: Dict[str, Any],
        prefix: str,
        layer: PolicyLayer,
        target_map: Dict[str, EffectivePolicyValue],
    ) -> None:
        for key, val in data.items():
            if key in ("policy_id", "policy_version", "effective_from"):
                continue
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(val, dict) and key not in ("humedad_comercial_base_por_cultivo",):
                self._flatten_and_merge(val, full_key, layer, target_map)
            else:
                target_map[full_key] = EffectivePolicyValue(
                    value=val,
                    source_scope=layer.scope,  # type: ignore
                    source_id=layer.source_id,
                    policy_id=layer.policy_id,
                    policy_version=layer.policy_version,
                )
