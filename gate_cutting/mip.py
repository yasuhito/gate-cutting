"""MIP-oriented cut selection helpers.

This module keeps optional solver dependencies out of import time.  The pure
helpers and greedy fallback are unit-testable without SciPy or NetworkX, while
``MIPCutFinder.build_graph`` / ``solve`` use them when available in the research
environment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .cut_selection import CircuitEdge, collect_cx_edges, cut_targets_from_edges
from .gate_cutting import CutTarget

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CutGraph:
    """Dependency-light representation of a circuit cutting graph."""

    num_qubits: int
    nodes: dict[int, dict[str, Any]]
    edges: list[CircuitEdge]


def build_cut_graph(
    circuit: Any,
    *,
    cx_fidelities: Mapping[tuple[int, int], float],
    one_q_fidelities: Mapping[int, float] | None = None,
    qubit_coords: Mapping[int, tuple[float, float]] | None = None,
) -> CutGraph:
    """Build a dependency-light cut graph from a Qiskit-like circuit."""

    one_q_fidelities = one_q_fidelities or {}
    qubit_coords = qubit_coords or {}

    nodes: dict[int, dict[str, Any]] = {}
    for qid in range(circuit.num_qubits):
        nodes[qid] = {
            "pos": qubit_coords.get(qid, (float(qid), 0.0)),
            "fidelity": float(one_q_fidelities.get(qid, 1.0)),
        }

    return CutGraph(
        num_qubits=circuit.num_qubits,
        nodes=nodes,
        edges=collect_cx_edges(circuit, cx_fidelities),
    )


def select_low_fidelity_cut_targets(
    edges: Sequence[CircuitEdge],
    *,
    max_cuts: int,
    cut_fidelity_threshold: float,
) -> list[CutTarget]:
    """Greedy fallback: cut the worst edges below the fidelity threshold."""

    if max_cuts <= 0:
        return []

    low_fidelity_edges = [edge for edge in edges if edge.fidelity < cut_fidelity_threshold]
    low_fidelity_edges.sort(key=lambda edge: edge.fidelity)
    return [
        CutTarget(instruction_index=edge.instruction_index, qubits=edge.qubits)
        for edge in low_fidelity_edges[:max_cuts]
    ]


class MIPCutFinder:
    """Find concrete CX cut targets using MIP when available, fallback otherwise."""

    def __init__(
        self,
        device_manager: Any | None = None,
        *,
        cx_fidelities: Mapping[tuple[int, int], float] | None = None,
        one_q_fidelities: Mapping[int, float] | None = None,
        qubit_coords: Mapping[int, tuple[float, float]] | None = None,
    ):
        if device_manager is not None:
            self.cx_fidelities = device_manager.cx_fidelities
            self.one_q_fidelities = device_manager.one_q_fidelities
            self.qubit_coords = device_manager.qubit_coords
        else:
            self.cx_fidelities = dict(cx_fidelities or {})
            self.one_q_fidelities = dict(one_q_fidelities or {})
            self.qubit_coords = dict(qubit_coords or {})

    def build_cut_graph(self, circuit: Any) -> CutGraph:
        return build_cut_graph(
            circuit,
            cx_fidelities=self.cx_fidelities,
            one_q_fidelities=self.one_q_fidelities,
            qubit_coords=self.qubit_coords,
        )

    def build_graph(self, circuit: Any):
        """Build a NetworkX MultiDiGraph for existing experiment visualizations."""

        try:
            import networkx as nx
        except ModuleNotFoundError as exc:  # pragma: no cover - env dependent.
            raise ModuleNotFoundError("networkx is required for build_graph(); use build_cut_graph() in lightweight tests") from exc

        cut_graph = self.build_cut_graph(circuit)
        graph = nx.MultiDiGraph()

        for qid, attrs in cut_graph.nodes.items():
            graph.add_node(qid, pos=attrs["pos"], fidelity=attrs["fidelity"])

        graph.graph["cx_edges"] = cut_graph.edges
        for edge in cut_graph.edges:
            control, target = edge.qubits
            graph.add_edge(
                control,
                target,
                gate="cx",
                fidelity=edge.fidelity,
                instruction_index=edge.instruction_index,
                source_instruction_index=edge.source_instruction_index,
                edge_index=edge.edge_index,
            )
        return graph

    def solve_cut_graph(
        self,
        cut_graph: CutGraph,
        *,
        max_cuts: int = 3,
        cut_fidelity_threshold: float = 0.96,
    ) -> list[CutTarget]:
        return select_low_fidelity_cut_targets(
            cut_graph.edges,
            max_cuts=max_cuts,
            cut_fidelity_threshold=cut_fidelity_threshold,
        )

    def _cut_targets_from_edge_indices(self, graph: Any, edges: Sequence[Any], selected_edge_indices: Sequence[int]) -> list[CutTarget]:
        cx_edges = getattr(graph, "graph", {}).get("cx_edges")
        if cx_edges is not None:
            return cut_targets_from_edges(cx_edges, selected_edge_indices=selected_edge_indices)

        cut_targets: list[CutTarget] = []
        for edge_index in selected_edge_indices:
            u, v, _, attr = edges[edge_index]
            cut_targets.append(
                CutTarget(
                    instruction_index=attr.get("instruction_index", edge_index),
                    qubits=(u, v),
                )
            )
        return cut_targets

    def solve(
        self,
        graph: Any,
        max_cuts: int = 3,
        cut_fidelity_threshold: float = 0.96,
    ) -> list[CutTarget]:
        """Solve cut selection on a NetworkX graph, using SciPy MILP if present."""

        if isinstance(graph, CutGraph):
            return self.solve_cut_graph(
                graph,
                max_cuts=max_cuts,
                cut_fidelity_threshold=cut_fidelity_threshold,
            )

        edges = list(graph.edges(keys=True, data=True))
        n_edges = len(edges)
        if n_edges == 0 or max_cuts <= 0:
            return []

        try:
            from scipy.optimize import Bounds, LinearConstraint, milp
            from scipy.sparse import coo_matrix
        except ModuleNotFoundError:
            logger.warning("SciPy not available. Falling back to greedy low-fidelity cut selection.")
            cx_edges = graph.graph.get("cx_edges")
            if cx_edges is not None:
                return select_low_fidelity_cut_targets(
                    cx_edges,
                    max_cuts=max_cuts,
                    cut_fidelity_threshold=cut_fidelity_threshold,
                )
            fallback_indices = [
                attr.get("edge_index", index)
                for index, (_, _, _, attr) in enumerate(edges)
                if attr.get("fidelity", 1.0) < cut_fidelity_threshold
            ][:max_cuts]
            return self._cut_targets_from_edge_indices(graph, edges, fallback_indices)

        nodes = list(graph.nodes(data=True))
        n_nodes = len(nodes)
        node_to_idx = {node_id: i for i, (node_id, _) in enumerate(nodes)}
        n_vars = n_nodes + n_edges

        c = np.zeros(n_vars)
        lower_bounds = np.zeros(n_vars)
        upper_bounds = np.ones(n_vars)

        bad_edges = []
        for k, (_, _, _, attr) in enumerate(edges):
            fidelity = attr.get("fidelity", 1.0)
            if fidelity < cut_fidelity_threshold:
                bad_edges.append((k, fidelity))
        bad_edges.sort(key=lambda item: item[1])
        force_cut_indices = {k for k, _ in bad_edges[:max_cuts]}

        for k, (_, _, _, attr) in enumerate(edges):
            fidelity = attr.get("fidelity", 1.0)
            z_idx = n_nodes + k
            if k in force_cut_indices:
                c[z_idx] = 0.0
                lower_bounds[z_idx] = 1.0
            else:
                error_rate = max(1.0 - fidelity, 1e-9)
                c[z_idx] = fidelity / error_rate

        rows: list[int] = []
        cols: list[int] = []
        vals: list[float] = []
        b_l: list[float] = []
        b_u: list[float] = []
        constraint_idx = 0

        for k, (u, v, _, _) in enumerate(edges):
            u_idx = node_to_idx[u]
            v_idx = node_to_idx[v]
            z_idx = n_nodes + k

            rows.extend([constraint_idx] * 3)
            cols.extend([u_idx, v_idx, z_idx])
            vals.extend([-1, 1, 1])
            b_l.append(0)
            b_u.append(np.inf)
            constraint_idx += 1

            rows.extend([constraint_idx] * 3)
            cols.extend([u_idx, v_idx, z_idx])
            vals.extend([1, -1, 1])
            b_l.append(0)
            b_u.append(np.inf)
            constraint_idx += 1

        for k in range(n_edges):
            rows.append(constraint_idx)
            cols.append(n_nodes + k)
            vals.append(1)
        b_l.append(0)
        b_u.append(max_cuts)
        constraint_idx += 1

        total_node_fidelity = sum(attrs.get("fidelity", 1.0) for _, attrs in nodes)
        for i, (_, attrs) in enumerate(nodes):
            rows.append(constraint_idx)
            cols.append(i)
            vals.append(attrs.get("fidelity", 1.0))
        b_l.append(0)
        b_u.append(total_node_fidelity)
        constraint_idx += 1

        matrix = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
        result = milp(
            c=c,
            constraints=LinearConstraint(matrix, b_l, b_u),
            integrality=np.ones(n_vars),
            bounds=Bounds(lower_bounds, upper_bounds),
        )

        if not result.success:
            logger.warning("MIP solver failed. Falling back to greedy low-fidelity cut selection.")
            cx_edges = graph.graph.get("cx_edges")
            if cx_edges is not None:
                return select_low_fidelity_cut_targets(
                    cx_edges,
                    max_cuts=max_cuts,
                    cut_fidelity_threshold=cut_fidelity_threshold,
                )
            return []

        selected_edge_indices = [
            edges[k][3].get("edge_index", k)
            for k in range(n_edges)
            if result.x[n_nodes + k] > 0.5
        ]
        if len(selected_edge_indices) > max_cuts:
            selected_edge_indices.sort(key=lambda edge_index: edges[edge_index][3].get("fidelity", 1.0))
            selected_edge_indices = selected_edge_indices[:max_cuts]

        return self._cut_targets_from_edge_indices(graph, edges, selected_edge_indices)
