import itertools
from typing import List, Dict, Set, Tuple, FrozenSet, Any


def _complement(literal: str) -> str:
    """Return the complementary literal.

    Positive literals are represented as "A", negated literals as "NOT_A".
    The complement of "A" is "NOT_A" and vice‑versa.
    """
    if literal.startswith("NOT_"):
        return literal[4:]
    return f"NOT_{literal}"


def _negate_literal(literal: str) -> str:
    """Negate a literal (used for negating the goal)."""
    return _complement(literal)


def _resolve_two_clauses(
    c1: FrozenSet[str], c2: FrozenSet[str]
) -> List[Tuple[Set[str], str]]:
    """Resolve two clauses and return a list of (resolvent_set, resolved_literal).

    For each complementary pair of literals present in the two clauses a new
    clause is produced by removing the complementary literals and taking the
    union of the remaining literals.
    """
    resolvents: List[Tuple[Set[str], str]] = []
    for lit in c1:
        comp = _complement(lit)
        if comp in c2:
            new_clause = (c1 - {lit}) | (c2 - {comp})
            # Use the positive form of the literal for reporting
            base_lit = lit if not lit.startswith("NOT_") else _complement(lit)
            resolvents.append((new_clause, base_lit))
    return resolvents


class ResolutionEngine:
    """Simple propositional resolution engine.

    Works with a knowledge base expressed as a list of clauses. Each clause is a
    list of literals, where a literal is either a positive identifier (e.g.
    "A") or a negated identifier prefixed with "NOT_" (e.g. "NOT_A").
    """

    def __init__(self):
        pass

    def resolution(self, knowledge_base: List[List[str]], goal: str) -> Dict[str, Any]:
        """Determine whether *goal* is entailed by *knowledge_base* using
        propositional resolution.

        Returns a dictionary with keys:
            - "goal": the original goal string
            - "entailed": True if the empty clause is derived from a branch that
              includes the negated goal, otherwise False
            - "derived_clauses": list of all unique clauses (as sorted lists)
            - "resolution_steps": list of dictionaries describing each
              successful resolution step
        """
        # Normalise KB into frozensets for fast set operations
        clause_set: Set[FrozenSet[str]] = {frozenset(cl) for cl in knowledge_base}

        # Add the negated goal as a clause
        negated = frozenset([_negate_literal(goal)])
        clause_set.add(negated)
        # Track clauses that are derived from the negated goal
        goal_related: Set[FrozenSet[str]] = {negated}

        derived_clauses: List[List[str]] = [sorted(list(c)) for c in clause_set]
        resolution_steps: List[Dict[str, Any]] = []
        empty_derived = False

        while True:
            new_clauses: Set[FrozenSet[str]] = set()
            clause_list = list(clause_set)
            for i, j in itertools.combinations(range(len(clause_list)), 2):
                c1 = clause_list[i]
                c2 = clause_list[j]
                for resolvent_set, resolved_lit in _resolve_two_clauses(c1, c2):
                    resolvent = frozenset(resolvent_set)
                    if resolvent in clause_set or resolvent in new_clauses:
                        continue
                    # Record step
                    resolution_steps.append({
                        "clause_1": sorted(list(c1)),
                        "clause_2": sorted(list(c2)),
                        "resolved_literal": resolved_lit,
                        "result": sorted(list(resolvent)),
                    })
                    # Propagate goal‑related flag
                    if c1 in goal_related or c2 in goal_related:
                        goal_related.add(resolvent)
                    if not resolvent:
                        # Empty clause derived
                        if resolvent in goal_related:
                            empty_derived = True
                        clause_set.add(resolvent)
                        derived_clauses.append([])
                        break
                    new_clauses.add(resolvent)
                if empty_derived:
                    break
            if empty_derived:
                break
            if not new_clauses:
                break
            for cl in new_clauses:
                clause_set.add(cl)
                derived_clauses.append(sorted(list(cl)))

        return {
            "goal": goal,
            "entailed": empty_derived,
            "derived_clauses": derived_clauses,
            "resolution_steps": resolution_steps,
        }
