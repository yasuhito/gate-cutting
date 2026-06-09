"""MIP-oriented cut selection helpers.

SciPy is a required dependency for solving cut selection.  The lightweight
``CutGraph`` helpers remain useful for tests and for keeping NetworkX out of
simple parsing paths, but every solver path goes through ``scipy.optimize.milp``.
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


@dataclass(frozen=True)
class _MipEdge:
    edge_index: int
    control: int
    target: int
    fidelity: float


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


def _scipy_milp_tools():
    try:
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_matrix
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency policy.
        raise ModuleNotFoundError(
            "scipy is required for MIP cut selection. Install scipy before running experiments."
        ) from exc

    return Bounds, LinearConstraint, coo_matrix, milp


class MIPCutFinder:
    """Find concrete CX cut targets using SciPy MILP."""

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
            raise ModuleNotFoundError("networkx is required for build_graph(); install networkx before running experiments") from exc

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

    def _solve_mip_edge_indices(
        self,
        nodes: Sequence[tuple[int, Mapping[str, Any]]],
        edges: Sequence[_MipEdge],
        *,
        max_cuts: int,
        cut_fidelity_threshold: float,
    ) -> list[int]:
        if not edges or max_cuts <= 0:
            return []

        Bounds, LinearConstraint, coo_matrix, milp = _scipy_milp_tools()

        node_to_idx = {node_id: index for index, (node_id, _) in enumerate(nodes)}
        n_nodes = len(nodes)
        n_edges = len(edges)
        n_vars = n_nodes + n_edges

        c = np.zeros(n_vars)
        for k, edge in enumerate(edges):
            z_idx = n_nodes + k
            if edge.fidelity < cut_fidelity_threshold:
                c[z_idx] = edge.fidelity - cut_fidelity_threshold
            else:
                c[z_idx] = 1e-6 + edge.fidelity - cut_fidelity_threshold

        rows: list[int] = []
        cols: list[int] = []
        vals: list[float] = []
        b_l: list[float] = []
        b_u: list[float] = []
        constraint_idx = 0

        for k, edge in enumerate(edges):
            u_idx = node_to_idx[edge.control]
            v_idx = node_to_idx[edge.target]
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

        matrix = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
        result = milp(
            c=c,
            constraints=LinearConstraint(matrix, b_l, b_u),
            integrality=np.ones(n_vars),
            bounds=Bounds(np.zeros(n_vars), np.ones(n_vars)),
        )

        if not result.success:
            message = getattr(result, "message", "unknown solver failure")
            raise RuntimeError(f"MIP solver failed: {message}")

        selected = [
            edge.edge_index
            for k, edge in enumerate(edges)
            if result.x[n_nodes + k] > 0.5
        ]
        logger.info("MIP selected %d cuts (max %d).", len(selected), max_cuts)
        return selected

    def solve_cut_graph(
        self,
        cut_graph: CutGraph,
        *,
        max_cuts: int = 3,
        cut_fidelity_threshold: float = 0.96,
    ) -> list[CutTarget]:
        mip_edges = [
            _MipEdge(
                edge_index=edge.edge_index,
                control=edge.qubits[0],
                target=edge.qubits[1],
                fidelity=edge.fidelity,
            )
            for edge in cut_graph.edges
        ]
        selected_edge_indices = self._solve_mip_edge_indices(
            list(cut_graph.nodes.items()),
            mip_edges,
            max_cuts=max_cuts,
            cut_fidelity_threshold=cut_fidelity_threshold,
        )
        return cut_targets_from_edges(cut_graph.edges, selected_edge_indices=selected_edge_indices)

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
                    fidelity=float(attr.get("fidelity", 1.0)),
                )
            )
        return cut_targets

    def solve(
        self,
        graph: Any,
        max_cuts: int = 3,
        cut_fidelity_threshold: float = 0.96,
    ) -> list[CutTarget]:
        """Solve cut selection with SciPy MILP."""

        if isinstance(graph, CutGraph):
            return self.solve_cut_graph(
                graph,
                max_cuts=max_cuts,
                cut_fidelity_threshold=cut_fidelity_threshold,
            )

        edges = list(graph.edges(keys=True, data=True))
        if not edges or max_cuts <= 0:
            return []

        mip_edges = [
            _MipEdge(
                edge_index=attr.get("edge_index", index),
                control=u,
                target=v,
                fidelity=float(attr.get("fidelity", 1.0)),
            )
            for index, (u, v, _, attr) in enumerate(edges)
        ]
        selected_edge_indices = self._solve_mip_edge_indices(
            list(graph.nodes(data=True)),
            mip_edges,
            max_cuts=max_cuts,
            cut_fidelity_threshold=cut_fidelity_threshold,
        )
        return self._cut_targets_from_edge_indices(graph, edges, selected_edge_indices)
