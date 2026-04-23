"""
Smart context chunker for LLM-based unit test generation.

Given a Python source file and a target (function or Class.method),
assembles the minimal, most relevant code context before prompt
construction — avoiding the token waste of passing the whole file.

Chunking modes
--------------
FUNCTION_ONLY          Only the target function + its imports.
FUNCTION_PLUS_DEPS     Target + every function it transitively calls.
CLASS_CONTEXT          Target class (stubs for siblings, full source for
                       __init__ and the target method) + top-level deps.
HIERARCHICAL_SUMMARY   Detailed context for relevant code, one-line
                       signatures for everything else.
TOKEN_BUDGET           Greedy BFS fill: highest-priority items first,
                       stop when token limit is reached.
FULL_SOURCE            Entire file (baseline / ablation).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from src.dependency_graph import DependencyGraph
from src.class_parser import ClassInfo, parse_classes, parse_target
from src.token_budget import TokenBudget, estimate_cost_usd, estimate_tokens


class ChunkMode(Enum):
    FUNCTION_ONLY         = "function_only"
    FUNCTION_PLUS_DEPS    = "function_plus_deps"
    CLASS_CONTEXT         = "class_context"
    HIERARCHICAL_SUMMARY  = "hierarchical_summary"
    TOKEN_BUDGET          = "token_budget"
    FULL_SOURCE           = "full_source"


@dataclass
class ChunkContext:
    # Identity
    target: str                              # original target string
    class_name: str | None                   # None for top-level functions
    function_name: str                       # bare method / function name

    # Core context
    target_source: str
    target_signature: str
    target_docstring: str

    # Supplementary context (assembled by chunking strategy)
    dependency_sources: list[str] = field(default_factory=list)
    class_header: str = ""    # condensed class shell
    imports: str = ""
    summary_context: str = "" # one-line stubs for irrelevant symbols

    # Metadata
    mode_used: ChunkMode = ChunkMode.FUNCTION_ONLY
    tokens_used: int = 0
    cost_estimate_usd: float = 0.0
    import_path: str = ""


class SmartChunker:
    """Assembles a ChunkContext for any target using the chosen ChunkMode."""

    DEFAULT_TOKEN_LIMIT = 6000

    def __init__(self, source_file: str, token_limit: int = DEFAULT_TOKEN_LIMIT) -> None:
        self._path = Path(source_file)
        self._source = self._path.read_text(encoding="utf-8")
        self._token_limit = token_limit
        self._graph = DependencyGraph(self._source)
        self._classes = parse_classes(self._source)

    def build(
        self,
        target: str,
        mode: ChunkMode,
        import_path: str = "",
    ) -> ChunkContext:
        """Build and return a ChunkContext for *target* using *mode*."""
        class_name, func_name = parse_target(target)
        qualified = f"{class_name}.{func_name}" if class_name else func_name

        target_src = self._graph.get_source(qualified) or ""
        sig, doc = self._extract_sig_doc(qualified, class_name, func_name)
        imports = self._graph.imports_source()

        ctx = ChunkContext(
            target=target,
            class_name=class_name,
            function_name=func_name,
            target_source=target_src,
            target_signature=sig,
            target_docstring=doc,
            imports=imports,
            mode_used=mode,
            import_path=import_path,
        )

        dispatch = {
            ChunkMode.FULL_SOURCE:          self._full_source,
            ChunkMode.FUNCTION_ONLY:        self._function_only,
            ChunkMode.FUNCTION_PLUS_DEPS:   self._function_plus_deps,
            ChunkMode.CLASS_CONTEXT:        self._class_context,
            ChunkMode.HIERARCHICAL_SUMMARY: self._hierarchical_summary,
            ChunkMode.TOKEN_BUDGET:         self._token_budget,
        }
        ctx = dispatch[mode](ctx, class_name, func_name, qualified)

        assembled = self._assemble_text(ctx)
        ctx.tokens_used = estimate_tokens(assembled)
        ctx.cost_estimate_usd = estimate_cost_usd(ctx.tokens_used)
        return ctx

    def _full_source(
        self, ctx: ChunkContext, *_
    ) -> ChunkContext:
        ctx.summary_context = self._source
        return ctx

    def _function_only(
        self, ctx: ChunkContext, *_
    ) -> ChunkContext:
        return ctx

    def _function_plus_deps(
        self, ctx: ChunkContext, _cn, _fn, qualified: str
    ) -> ChunkContext:
        ctx.dependency_sources = self._dep_sources(qualified)
        return ctx

    def _class_context(
        self, ctx: ChunkContext, class_name: str | None, func_name: str, qualified: str
    ) -> ChunkContext:
        all_deps = self._graph.dependencies(qualified)
        # Sibling methods the target directly calls — need full source, not stubs
        called_siblings = {
            dep for dep in self._graph.dependencies(qualified, max_depth=1)
            if self._graph.class_of(dep) == class_name
        }
        if class_name and class_name in self._classes:
            ctx.class_header = self._format_class_header(
                self._classes[class_name], func_name, called_siblings
            )
        # Top-level (non-class) dependencies
        ctx.dependency_sources = [
            src for dep in all_deps
            if self._graph.class_of(dep) != class_name
            if (src := self._graph.get_source(dep)) is not None
        ]
        return ctx

    def _hierarchical_summary(
        self, ctx: ChunkContext, class_name: str | None, func_name: str, qualified: str
    ) -> ChunkContext:
        ctx = self._class_context(ctx, class_name, func_name, qualified)
        relevant = {qualified} | set(self._graph.dependencies(qualified))
        stubs = []
        for name in self._graph.all_names():
            if name not in relevant:
                sig, doc = self._extract_sig_doc(name, *parse_target(name))
                line = f"# {name}: {sig}"
                if doc:
                    line += f"  # {doc[:80]}"
                stubs.append(line)
        if stubs:
            ctx.summary_context = "# OTHER MODULE SYMBOLS (signatures only):\n" + "\n".join(stubs)
        return ctx

    def _token_budget(
        self, ctx: ChunkContext, class_name: str | None, func_name: str, qualified: str
    ) -> ChunkContext:
        """Greedily fill context up to the token limit in priority order."""
        budget = TokenBudget(self._token_limit)
        budget.consume(ctx.target_source)
        budget.consume(ctx.imports)

        # Priority 1: __init__ (needed to understand class state)
        if class_name and class_name in self._classes:
            init = self._classes[class_name].methods.get("__init__")
            if init and budget.fits(init.source):
                budget.consume(init.source)
                ctx.class_header = init.source

        # Priority 2: direct deps (depth=1)
        direct = self._graph.dependencies(qualified, max_depth=1)
        dep_sources: list[str] = []
        for dep in direct:
            src = self._graph.get_source(dep)
            if src and budget.consume(src):
                dep_sources.append(src)

        # Priority 3: transitive deps (depth 2-3) if budget permits
        transitive = self._graph.dependencies(qualified, max_depth=3)[len(direct):]
        for dep in transitive:
            src = self._graph.get_source(dep)
            if src and budget.consume(src):
                dep_sources.append(src)

        ctx.dependency_sources = dep_sources
        return ctx

    def _dep_sources(self, qualified: str) -> list[str]:
        return [
            src for dep in self._graph.dependencies(qualified)
            if (src := self._graph.get_source(dep)) is not None
        ]

    def _extract_sig_doc(
        self, qualified: str, class_name: str | None, func_name: str
    ) -> tuple[str, str]:
        if class_name and class_name in self._classes:
            method = self._classes[class_name].methods.get(func_name)
            if method:
                return method.signature, method.docstring
        node = self._graph._nodes.get(qualified if not class_name else func_name)
        if node:
            args = ast.unparse(node.args)
            ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
            return f"def {node.name}({args}){ret}", ast.get_docstring(node) or ""
        return "", ""

    def _format_class_header(
        self,
        cls_info: ClassInfo,
        target_method: str,
        called_siblings: set | None = None,
    ) -> str:
        """
        Condensed class shell: full source for __init__, the target method,
        and any sibling methods it directly calls; one-line stubs for the rest.
        """
        show_full = {"__init__", target_method} | (called_siblings or set())
        # strip class prefix so names match cls_info.methods keys
        show_full = {n.split(".")[-1] for n in show_full}

        bases_str = f"({', '.join(cls_info.bases)})" if cls_info.bases else ""
        lines = [f"class {cls_info.name}{bases_str}:"]
        if cls_info.docstring:
            lines.append(f'    """{cls_info.docstring}"""')
            lines.append("")

        for name, method in cls_info.methods.items():
            if name in show_full:
                for src_line in method.source.splitlines():
                    lines.append(f"    {src_line}")
            else:
                stub = f"    {method.signature}"
                if method.docstring:
                    stub += f"\n        # {method.docstring[:100]}"
                stub += "\n        ..."
                lines.append(stub)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _assemble_text(ctx: ChunkContext) -> str:
        parts = [ctx.imports, ctx.class_header, ctx.target_source]
        parts.extend(ctx.dependency_sources)
        parts.append(ctx.summary_context)
        return "\n".join(p for p in parts if p)
