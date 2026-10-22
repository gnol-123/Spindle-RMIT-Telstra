"""Projects and the agent nodes provisioned inside them."""

import asyncio
import logging
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import anyio
from anyio import to_thread
from fastapi import APIRouter, HTTPException, Query, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, StringConstraints

from app.environments import lifecycle
from app.repositories.project_repo import (
    AgentType,
    DuplicateEdge,
    DuplicateProjectName,
    Edge,
    Node,
    Project,
    UsageTotal,
)
from app.repositories.tool_repo import (
    ToolNode,
    ToolPreset,
    ToolRepository,
    ToolType,
    load_node_secrets,
)
from app.routers.auth import CurrentAuth
from app.routers.chat import ChatMessage
from app.routers.deps import EnvRepo, ProjectRepo, ToolRepo, TurnRepos
from app.routers.environments import EnvironmentNodeResponse, create_environment_node
from app.services import intake, previews_storage
from app.services.models import ModelsUnavailable, list_models
from app.tools.base import ToolContext
from app.tools.mcp.base import POOLED_VERIFY
from app.tools.oauth_refresh import TokenExchangeError, with_access_token
from app.tools.registry import get_spec, platform_secrets
from app.workflows import cancel_for_node, cancel_for_project, refresh_edge

router = APIRouter(tags=["projects"])

log = logging.getLogger(__name__)

# Where default tool boxes land relative to their agent. Overlap is the
# frontend's problem.
_DEFAULT_TOOL_DX = -260
_DEFAULT_TOOL_DY = 90


# -- PROJECTS ------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    preview_url: str | None = None

    @classmethod
    def of(cls, p: Project, preview_url: str | None = None) -> "ProjectResponse":
        return cls(id=UUID(p.id), name=p.name, preview_url=preview_url)


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    req: CreateProjectRequest, repo: ProjectRepo, env_repo: EnvRepo
) -> ProjectResponse:
    try:
        project = await to_thread.run_sync(lambda: repo.create_project(req.name, req.description))
    except DuplicateProjectName as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a project named '{req.name}'",
        ) from exc

    # Every project owns a scratch space. Not provisioned yet: pending costs nothing.
    await to_thread.run_sync(lambda: env_repo.ensure_scratch_node(project.id, new_project=True))
    return ProjectResponse.of(project)


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(repo: ProjectRepo) -> list[ProjectResponse]:
    projects = await to_thread.run_sync(repo.list_projects)
    # App screenshot first, then the canvas snapshot. The canvas file is
    # overwritten in place, so its snapshot time versions the cached URL.
    paths = {
        (p.thumbnail_path or f"{p.id}/{_CANVAS_FILE}"): (
            None if p.thumbnail_path else p.canvas_snapshot_at
        )
        for p in projects
        if p.thumbnail_path or p.canvas_snapshot_at
    }
    urls: dict[str, str] = {}
    if paths:
        try:
            urls = await to_thread.run_sync(previews_storage.sign_cached, paths)
        except Exception:
            log.warning("preview signing failed; listing without previews", exc_info=True)
    return [
        ProjectResponse.of(p, urls.get(p.thumbnail_path or f"{p.id}/{_CANVAS_FILE}"))
        for p in projects
    ]


# Stripped first, so blank input is a 422.
_Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class RenameProjectRequest(BaseModel):
    name: _Name


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def rename_project(
    project_id: UUID, req: RenameProjectRequest, repo: ProjectRepo
) -> ProjectResponse:
    """Rename a project. The card keeps its own preview_url."""
    try:
        project = await to_thread.run_sync(repo.rename_project, str(project_id), req.name)
    except DuplicateProjectName as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a project named '{req.name}'",
        ) from exc
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectResponse.of(project)


_CANVAS_FILE = "canvas.webp"
_SNAPSHOT_TYPES = {"image/webp", "image/png", "image/jpeg"}
_SNAPSHOT_MAX = 2_000_000


@router.put("/projects/{project_id}/canvas-snapshot", status_code=status.HTTP_204_NO_CONTENT)
async def put_canvas_snapshot(project_id: UUID, request: Request, repo: ProjectRepo) -> None:
    """Store a canvas screenshot as the project's card preview. Raw image body."""
    project = await to_thread.run_sync(repo.get_project, str(project_id))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in _SNAPSHOT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Send image/webp, image/png or image/jpeg",
        )
    too_big = HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Snapshot is over 2 MB"
    )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > _SNAPSHOT_MAX:
        raise too_big
    data = await request.body()
    if len(data) > _SNAPSHOT_MAX:
        raise too_big
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty body")

    try:
        await to_thread.run_sync(
            previews_storage.upload_canvas_snapshot, str(project_id), data, content_type
        )
    except Exception as exc:
        log.exception("canvas snapshot upload failed for project %s", project_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Snapshot storage failed"
        ) from exc
    await to_thread.run_sync(repo.set_canvas_snapshot_at, str(project_id))


# Stripped first, so blank input is a 422.
_Prompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ClassifyRequest(BaseModel):
    text: _Prompt


class ClassifyResponse(BaseModel):
    kind: Literal["name", "build"]


@router.post("/projects/classify", response_model=ClassifyResponse)
async def classify_prompt(req: ClassifyRequest, _auth: CurrentAuth) -> ClassifyResponse:
    """Is the new-project prompt a title or an app idea."""
    return ClassifyResponse(kind=await intake.classify(req.text))


class BuildProjectRequest(BaseModel):
    idea: _Prompt


class BuildProjectResponse(BaseModel):
    project: ProjectResponse
    orchestrator_node_id: UUID


@router.post(
    "/projects/build", response_model=BuildProjectResponse, status_code=status.HTTP_201_CREATED
)
async def build_project(
    req: BuildProjectRequest, repo: ProjectRepo, tool_repo: ToolRepo, env_repo: EnvRepo
) -> BuildProjectResponse:
    """Name a project after the idea and seed it with an orchestrator."""
    agent_type = await to_thread.run_sync(repo.get_agent_type, "orchestrator")
    if agent_type is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orchestrator agent type is missing from the catalog",
        )

    name = await intake.title_for(req.idea)
    try:
        project = await to_thread.run_sync(lambda: repo.create_project(name))
    except DuplicateProjectName:
        try:
            project = await to_thread.run_sync(lambda: repo.create_project(f"{name} 2"))
        except DuplicateProjectName as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"You already have a project named '{name}'",
            ) from exc

    # provision_agent ensures the scratch node. An empty project left behind
    # would push retries to "Name 2", so undo it on failure.
    try:
        node_id = await provision_agent(
            project.id,
            agent_type,
            agent_type.name,
            position_x=0,
            position_y=0,
            tool_policy="auto",
            repo=repo,
            tool_repo=tool_repo,
            env_repo=env_repo,
        )
    except Exception:
        await to_thread.run_sync(repo.delete_project, project.id)
        raise
    return BuildProjectResponse(
        project=ProjectResponse.of(project), orchestrator_node_id=UUID(node_id)
    )


async def _wrong_kind_detail(node_id: UUID, tool_repo: ToolRepo, env_repo: EnvRepo) -> str:
    """Explain a PATCH miss: wrong route, or genuinely no such node."""
    env = await to_thread.run_sync(env_repo.get_environment_node, str(node_id))
    if env is not None:
        return (
            "That node is an environment, and this route updates agents. "
            "Use PATCH /projects/{project_id}/environments/{node_id}."
        )
    tool = await to_thread.run_sync(tool_repo.get_tool_node, str(node_id))
    if tool is not None:
        return (
            "That node is a tool, and this route updates agents. A tool node has no "
            "patch route: re-check it with POST /projects/{project_id}/nodes/{node_id}/verify, "
            "or delete it and create it again to change its config."
        )
    return "Node not found"


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, repo: ProjectRepo, env_repo: EnvRepo) -> None:
    """Delete a project, cascading to its nodes, edges, conversations and messages."""
    # Stop every running turn first: otherwise it keeps writing into a
    # conversation the delete is about to cascade away. Every environment on
    # the canvas is read before the rows cascade away and the sandbox ids go.
    _, environments = await asyncio.gather(
        cancel_for_project(str(project_id)),
        to_thread.run_sync(env_repo.list_environment_nodes, str(project_id)),
    )
    # teardown never raises, so gather cannot abandon a sibling.
    await asyncio.gather(*(lifecycle.teardown(env_repo, env) for env in environments))

    deleted = await to_thread.run_sync(repo.delete_project, str(project_id))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Thumbnails outlive the row cascade: best effort.
    try:
        await to_thread.run_sync(previews_storage.remove_project, str(project_id))
    except Exception:
        log.exception("preview storage cleanup failed for project %s", project_id)


# -- AGENT NODES ---------------------------------------------------------------


class AgentTypeResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    default_presets: list[str] = []

    @classmethod
    def of(cls, a: AgentType) -> "AgentTypeResponse":
        return cls(id=UUID(a.id), slug=a.slug, name=a.name, default_presets=a.default_presets)


class CreateNodeRequest(BaseModel):
    kind: Literal["agent", "tool", "environment"] = "agent"
    # The catalog slug, so the frontend need not resolve UUIDs to provision.
    # Required for kind='agent'.
    agent_slug: str | None = Field(default=None, min_length=1, max_length=50)
    # Required for kind='tool'.
    tool_slug: str | None = Field(default=None, min_length=1, max_length=50)
    # kind='tool' alternative to tool_slug: instantiate a library preset.
    preset_slug: str | None = Field(default=None, min_length=1, max_length=50)
    # kind='tool' only. Non-secret keys go to nodes.config, secret keys to the vault.
    config: dict[str, Any] = Field(default_factory=dict)
    # Defaults to the template's name if omitted.
    name: str | None = Field(default=None, min_length=1, max_length=200)
    position_x: float = 0
    position_y: float = 0
    # Agent nodes only. 'auto' for an orchestrator that should run unattended.
    tool_policy: Literal["ask", "auto"] = "ask"


class UpdateNodeRequest(BaseModel):
    """Partial update. Only the fields sent are changed. node_type and owner_id are fixed."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    position_x: float | None = None
    position_y: float | None = None
    tool_policy: Literal["ask", "auto"] | None = None
    model: str | None = Field(default=None, max_length=200)


class NodeResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    agent_slug: str | None = None
    tool_policy: str
    position_x: float
    position_y: float
    kind: str = "agent"
    # Lifecycle. Agents and tools are 'ready';
    # pending, provisioning, ready, error and stopped.
    status: str = "ready"
    status_detail: str | None = None
    # Role variable for envNodes user | scratch
    # scratch is the default env that all agents have to spin up artifacts
    # user is the user provisioned environment for any task requiring an environment
    role: str | None = None
    runtime: str | None = None
    # The model this node actually runs on: its own override, else its type's.
    model: str | None = None

    @classmethod
    def of(cls, n: Node, agent_slug: str | None = None) -> "NodeResponse":
        """agent_slug defaults to the node's join; pass it on create, before the re-read."""
        config = n.config if n.kind == "environment" else {}
        return cls(
            id=UUID(n.id),
            project_id=UUID(n.project_id),
            name=n.name,
            agent_slug=agent_slug if agent_slug is not None else n.agent_slug,
            tool_policy=n.tool_policy,
            position_x=n.position_x,
            position_y=n.position_y,
            kind=n.kind,
            status=n.status,
            status_detail=n.status_detail,
            role=config.get("role"),
            runtime=config.get("runtime"),
            model=n.model or None,
        )


class ToolTypeResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None = None
    config_schema: dict[str, Any]
    secret_fields: list[str]
    # token: render a password field. oauth2: render a Connect button.
    auth_kind: str = "token"

    @classmethod
    def of(cls, t: ToolType) -> "ToolTypeResponse":
        return cls(
            id=UUID(t.id),
            slug=t.slug,
            name=t.name,
            description=t.description,
            config_schema=t.config_schema,
            secret_fields=t.secret_fields,
            auth_kind=t.auth_kind,
        )


class ToolPresetResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None = None
    tool_slug: str
    config: dict[str, Any]

    @classmethod
    def of(cls, p: ToolPreset) -> "ToolPresetResponse":
        return cls(
            id=UUID(p.id),
            slug=p.slug,
            name=p.name,
            description=p.description,
            tool_slug=p.tool_slug,
            config=p.config,
        )


class ToolNodeResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    kind: str = "tool"
    tool_slug: str
    config: dict[str, Any]
    status: str
    status_detail: str | None = None
    # Names only. Values are never returned.
    secrets_set: list[str] = []
    # Platform keys in effect that the user has not overridden.
    platform_provided: list[str] = []

    @classmethod
    def of(cls, n: ToolNode, secrets_set: list[str]) -> "ToolNodeResponse":
        provided = sorted(k for k in platform_secrets(n.tool_slug) if k not in secrets_set)
        return cls(
            id=UUID(n.id),
            project_id=UUID(n.project_id),
            name=n.name,
            tool_slug=n.tool_slug,
            config=n.config,
            status=n.status,
            status_detail=n.status_detail,
            secrets_set=secrets_set,
            platform_provided=provided,
        )


@router.get("/agent-types", response_model=list[AgentTypeResponse])
async def list_agent_types(repo: ProjectRepo) -> list[AgentTypeResponse]:
    """The palette of agent templates a node can be provisioned from."""
    types = await to_thread.run_sync(repo.list_agent_types)
    return [AgentTypeResponse.of(t) for t in types]


async def provision_agent(
    project_id: str,
    agent_type: AgentType,
    name: str,
    *,
    position_x: float,
    position_y: float,
    tool_policy: str,
    repo: ProjectRepo,
    tool_repo: ToolRepo,
    env_repo: EnvRepo,
) -> str:
    """Create an agent box with its conversation, scratch access and default tools.

    The agent branch of POST /nodes, shared with the canvas tool so an
    orchestrator-made agent is indistinguishable from a user-made one.
    """
    req = CreateNodeRequest(
        agent_slug=agent_type.slug, position_x=position_x, position_y=position_y
    )

    # The scratch lookup and the default tool nodes don't need the agent id,
    # so they run alongside the node insert.
    node_res, scratch, tools = await asyncio.gather(
        to_thread.run_sync(
            lambda: repo.create_node(
                project_id,
                agent_type.id,
                name,
                position_x=position_x,
                position_y=position_y,
                tool_policy=tool_policy,
                with_conversation=False,
            )
        ),
        to_thread.run_sync(lambda: env_repo.ensure_scratch_node(project_id)),
        _create_default_tools(project_id, agent_type, req, tool_repo),
        return_exceptions=True,
    )
    failed = next((r for r in (node_res, scratch, tools) if isinstance(r, BaseException)), None)
    if failed is not None:
        if isinstance(tools, list) and tools:
            log.error("agent create failed; orphan tool nodes %s", [t.id for t in tools])
        raise failed
    node_id: str = node_res

    # Conversation and edges both only need the node id.
    await asyncio.gather(
        to_thread.run_sync(lambda: repo.create_conversation(node_id, project_id)),
        _wire_agent(node_id, scratch.id, [t.id for t in tools], repo),
    )
    _verify_in_background(tools, tool_repo)
    return node_id


async def _wire_agent(
    node_id: str, scratch_id: str, tool_ids: list[str], repo: ProjectRepo
) -> None:
    # Access requires an edge, so the scratch space is wired like any other
    # environment. The frontend hides this one rather than drawing it.
    edges = [(scratch_id, node_id, "environment"), *((t, node_id, "tool") for t in tool_ids)]
    try:
        await to_thread.run_sync(repo.create_edges, edges)
    except Exception:
        log.warning("bulk edge insert failed for agent %s; retrying one by one", node_id)
        for src, tgt, kind in edges:
            try:
                await to_thread.run_sync(lambda a=(src, tgt, kind): repo.create_edge(*a))
            except DuplicateEdge:
                # A retried create. The wiring is already there.
                pass
            except Exception:
                if kind == "environment":
                    raise
                # The tool node exists with no edge. Named so it can be cleaned up.
                log.exception("edge failed; orphan tool node %s", src)


@router.post(
    "/projects/{project_id}/nodes",
    response_model=NodeResponse | ToolNodeResponse | EnvironmentNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_node(
    project_id: UUID,
    req: CreateNodeRequest,
    repo: ProjectRepo,
    tool_repo: ToolRepo,
    env_repo: EnvRepo,
) -> NodeResponse | ToolNodeResponse | EnvironmentNodeResponse:
    """Provision a box on a project's canvas: kind='agent', 'tool' or 'environment'."""
    # The agent type read doesn't depend on the project one; sleep(0) is a None placeholder.
    agent_slug = req.agent_slug if req.kind == "agent" else None
    project, agent_type = await asyncio.gather(
        to_thread.run_sync(repo.get_project, str(project_id)),
        to_thread.run_sync(repo.get_agent_type, agent_slug) if agent_slug else asyncio.sleep(0),
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if req.kind == "tool":
        return await _create_tool_node(project_id, req, tool_repo)

    if req.kind == "environment":
        return await create_environment_node(project_id, req, env_repo)

    if not req.agent_slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="agent_slug is required for kind='agent'",
        )

    if agent_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent '{req.agent_slug}'",
        )

    name = req.name or agent_type.name
    node_id = await provision_agent(
        str(project_id),
        agent_type,
        name,
        position_x=req.position_x,
        position_y=req.position_y,
        tool_policy=req.tool_policy,
        repo=repo,
        tool_repo=tool_repo,
        env_repo=env_repo,
    )

    # Built from the template and the request: the insert has nothing else to say.
    node = Node(
        id=node_id,
        project_id=str(project_id),
        name=name,
        agent_type_id=agent_type.id,
        system_prompt=agent_type.system_prompt,
        model=agent_type.model,
        tool_policy=req.tool_policy,
        position_x=req.position_x,
        position_y=req.position_y,
        agent_slug=agent_type.slug,
    )
    return NodeResponse.of(node)


class UsageModelResponse(BaseModel):
    """Totals for one model. `reasoning_tokens` is inside `output_tokens`."""

    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    requests: int
    message_count: int


class UsageResponse(BaseModel):
    """Per-model breakdown plus totals of the columns that are safely additive.

    No grand total of output+reasoning: reasoning is a subset of output, so
    adding them double-counts. Totals across models are token counts only,
    never a cost: prices differ per model, so a cap set on these numbers is a
    token budget, not a spend budget.

    `project_id` is null on the account-wide route.
    """

    project_id: UUID | None = None
    by_model: list[UsageModelResponse]
    input_tokens: int
    output_tokens: int
    message_count: int

    @classmethod
    def of(cls, totals: list[UsageTotal], project_id: UUID | None = None) -> "UsageResponse":
        return cls(
            project_id=project_id,
            by_model=[UsageModelResponse(**vars(t)) for t in totals],
            input_tokens=sum(t.input_tokens for t in totals),
            output_tokens=sum(t.output_tokens for t in totals),
            message_count=sum(t.message_count for t in totals),
        )


@router.get("/usage", response_model=UsageResponse)
async def get_user_usage(repo: ProjectRepo) -> UsageResponse:
    """This user's token usage across every project. What a cap reads.

    Already scoped to the caller: there is no route to another user's usage.
    """
    return UsageResponse.of(await to_thread.run_sync(repo.get_user_usage))


@router.get("/projects/{project_id}/usage", response_model=UsageResponse)
async def get_usage(project_id: UUID, repo: ProjectRepo) -> UsageResponse:
    """This user's token usage in one project, broken down by model."""
    project, totals = await asyncio.gather(
        to_thread.run_sync(repo.get_project, str(project_id)),
        to_thread.run_sync(repo.get_usage, str(project_id)),
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return UsageResponse.of(totals, project_id)


@router.get("/projects/{project_id}/nodes", response_model=list[NodeResponse])
async def list_nodes(project_id: UUID, repo: ProjectRepo) -> list[NodeResponse]:
    """List every box on a project's canvas, agents and tools."""
    project, nodes = await asyncio.gather(
        to_thread.run_sync(repo.get_project, str(project_id)),
        to_thread.run_sync(repo.list_nodes, str(project_id)),
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return [NodeResponse.of(n) for n in nodes]


@router.get("/projects/{project_id}/nodes/{node_id}/messages", response_model=list[ChatMessage])
async def list_node_messages(
    project_id: UUID,
    node_id: UUID,
    turn_repos: TurnRepos,
    after_seq: int = Query(default=0, ge=0),
) -> list[ChatMessage]:
    """An agent node's transcript, oldest first. ``after_seq`` for polling.

    Reads on the service client (TurnRepos). Predates user clients sharing a
    pool (see supabase._user_http); either is warm now.

    No separate project lookup: get_agent_node is owner-filtered and
    its project_id is checked below.
    """
    repo = turn_repos.project
    node = await to_thread.run_sync(repo.get_agent_node, str(node_id))
    if node is None or node.project_id != str(project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    conversation_id = node.conversation_id or await to_thread.run_sync(
        repo.get_conversation_for_node, node.id
    )
    if conversation_id is None:
        return []
    messages = await to_thread.run_sync(
        lambda: repo.list_messages_after(conversation_id, after_seq=after_seq)
    )
    return [ChatMessage.of(m) for m in messages]


@router.patch("/projects/{project_id}/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    project_id: UUID,
    node_id: UUID,
    req: UpdateNodeRequest,
    repo: ProjectRepo,
    tool_repo: ToolRepo,
    env_repo: EnvRepo,
) -> NodeResponse:
    """Move, rename, set the tool policy, or set the model. Empty body is a no-op.

    A model is checked against the provider's catalogue first, so a typo is a
    422 here rather than a failed turn later. "" clears the override.
    """
    changes = req.model_dump(exclude_none=True)
    if req.model:
        try:
            available = await list_models()
        except ModelsUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The model catalogue is unavailable, so a model cannot be validated.",
            ) from exc
        if req.model not in available:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown model '{req.model}'. Available: {', '.join(available)}",
            )

    node = await to_thread.run_sync(lambda: repo.update_node(str(node_id), changes))
    if node is None:
        # This route only updates agents. A miss is usually the right node on
        # the wrong URL, so say which route owns it rather than "not found".
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=await _wrong_kind_detail(node_id, tool_repo, env_repo),
        )
    return NodeResponse.of(node)


class DeleteNodeResponse(BaseModel):
    # The clicked node, plus any tool nodes orphaned by removing it.
    deleted_node_ids: list[UUID]


@router.delete(
    "/projects/{project_id}/nodes/{node_id}",
    response_model=DeleteNodeResponse,
)
async def delete_node(
    project_id: UUID, node_id: UUID, repo: ProjectRepo, env_repo: EnvRepo
) -> DeleteNodeResponse:
    """Remove a node of any kind, cascading to its conversation, transcript and secrets."""
    # Stop a running turn first: only agent nodes have a conversation, so a
    # tool/environment node's None id is a no-op.
    conversation_id, env = await asyncio.gather(
        to_thread.run_sync(repo.get_conversation_for_node, str(node_id)),
        to_thread.run_sync(env_repo.get_environment_node, str(node_id)),
    )
    # Kill the sandbox first: the row is about to go, and nothing else knows
    # the id. teardown never raises, so a dead E2B cannot block the delete.
    await asyncio.gather(
        cancel_for_node(conversation_id),
        *([lifecycle.teardown(env_repo, env)] if env is not None else []),
    )

    deleted = await to_thread.run_sync(repo.delete_node, str(node_id))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return DeleteNodeResponse(deleted_node_ids=deleted)


# -- TOOL NODES ------------------------------------------------------------------


def _split_tool_config(
    tool_type: ToolType, config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Split config into plain fields and secrets. Unknown keys are rejected."""
    schema_fields = {f["key"] for f in (tool_type.config_schema.get("fields") or [])}
    secret_field_names = set(tool_type.secret_fields)
    known = schema_fields | secret_field_names

    unknown = set(config) - known
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown config field(s): {', '.join(sorted(unknown))}",
        )

    plain: dict[str, Any] = {}
    secrets: dict[str, str] = {}
    for key, value in config.items():
        if key in secret_field_names:
            secrets[key] = value
        else:
            plain[key] = value
    return plain, secrets


def _with_default_url(tool_type: ToolType, config: dict[str, Any]) -> dict[str, Any]:
    default_url = tool_type.config_schema.get("default_url")
    if default_url and not config.get("url"):
        return {**config, "url": default_url}
    return config


async def _provision_tool_node(
    project_id: str,
    tool_type: ToolType,
    name: str,
    config: dict[str, Any],
    secrets: dict[str, str],
    *,
    position_x: float,
    position_y: float,
    tool_repo: ToolRepo,
    verify: bool = True,
) -> str:
    """Create a tool row, store its secrets, verify it. Returns the node id.

    Shared by the request path and default wiring. ``config`` is already
    split: plain fields only, with any preset config merged in.
    """
    # Copy the catalog default url when config omits one, keeping the node
    # self-contained against later catalog edits.
    config = _with_default_url(tool_type, config)

    node_id = await to_thread.run_sync(
        lambda: tool_repo.create_tool_node(
            project_id,
            tool_type.id,
            name,
            config,
            position_x=position_x,
            position_y=position_y,
        )
    )

    for key, value in secrets.items():
        await to_thread.run_sync(lambda k=key, v=value: tool_repo.set_secret(node_id, k, v))

    if verify:
        await _verify_tool_node(node_id, tool_repo)
    return node_id


async def _create_tool_node(
    project_id: UUID,
    req: CreateNodeRequest,
    tool_repo: ToolRepo,
) -> ToolNodeResponse:
    """Provision a tool box from a type or a preset: split config, verify."""
    if not req.tool_slug and not req.preset_slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="tool_slug or preset_slug is required for kind='tool'",
        )
    if req.tool_slug and req.preset_slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Send tool_slug or preset_slug, not both",
        )

    preset = None
    tool_slug = req.tool_slug
    if req.preset_slug:
        preset = await to_thread.run_sync(tool_repo.get_preset, req.preset_slug)
        if preset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown preset '{req.preset_slug}'",
            )
        tool_slug = preset.tool_slug

    tool_type = await to_thread.run_sync(tool_repo.get_tool_type, tool_slug)
    if tool_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown tool '{tool_slug}'",
        )

    plain_config, secrets = _split_tool_config(tool_type, req.config)
    if preset is not None:
        # Preset is the base, the request overrides. Preset config is trusted
        # and merged after the split, so it is not checked against the form.
        plain_config = {**preset.config, **plain_config}

    name = req.name or (preset.name if preset else tool_type.name)
    node_id = await _provision_tool_node(
        str(project_id),
        tool_type,
        name,
        plain_config,
        secrets,
        position_x=req.position_x,
        position_y=req.position_y,
        tool_repo=tool_repo,
    )

    node = await to_thread.run_sync(tool_repo.get_tool_node, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Node could not be read back after creation",
        )
    secrets_set = await to_thread.run_sync(tool_repo.secret_keys, node_id)
    return ToolNodeResponse.of(node, secrets_set)


async def _load_catalog(
    tool_repo: ToolRepository,
) -> tuple[dict[str, ToolPreset], dict[str, ToolType]]:
    """The preset and tool type catalogs, keyed by slug. Two reads, not two per preset."""
    presets, tool_types = await asyncio.gather(
        to_thread.run_sync(tool_repo.list_presets),
        to_thread.run_sync(tool_repo.list_tool_types),
    )
    return {p.slug: p for p in presets}, {t.slug: t for t in tool_types}


async def _create_default_tools(
    project_id: str,
    agent_type: AgentType,
    req: CreateNodeRequest,
    tool_repo: ToolRepo,
) -> list[ToolNode]:
    """Create the tool nodes for the presets an agent type lists. Returns them, unread.

    One bulk insert. If it fails, each preset is retried on its own: an
    unknown slug or a failed create is logged and skipped, never raised, so a
    typo in a seed cannot block creating an agent. Not transactional: a
    half-wired agent is visible and deletable. Nothing here is idempotent: a
    retried request creates a second agent and a second set of defaults.
    Defaults carry no secrets, so there is nothing to store or verify inline.
    """
    if not agent_type.default_presets:
        return []

    presets, tool_types = await _load_catalog(tool_repo)

    # Slot index is fixed up front so positions don't depend on completion order.
    planned: list[tuple[ToolPreset, ToolType, float, float]] = []
    for slug in agent_type.default_presets:
        preset = presets.get(slug)
        if preset is None:
            log.warning("agent type %s lists unknown preset %s", agent_type.slug, slug)
            continue
        tool_type = tool_types.get(preset.tool_slug)
        if tool_type is None:
            log.warning("preset %s names unknown tool type %s", slug, preset.tool_slug)
            continue
        planned.append(
            (
                preset,
                tool_type,
                req.position_x + _DEFAULT_TOOL_DX,
                req.position_y + len(planned) * _DEFAULT_TOOL_DY,
            )
        )
    if not planned:
        return []

    rows = [
        {
            "tool_type_id": tool_type.id,
            "name": preset.name,
            "config": _with_default_url(tool_type, dict(preset.config)),
            "position_x": x,
            "position_y": y,
        }
        for preset, tool_type, x, y in planned
    ]

    # Built from what was inserted, so background verify skips a re-read.
    def node(node_id: str, row: dict, tool_type: ToolType) -> ToolNode:
        return ToolNode(
            id=node_id,
            project_id=project_id,
            name=row["name"],
            tool_type_id=tool_type.id,
            tool_slug=tool_type.slug,
            config=row["config"],
            status="pending",
            status_detail=None,
        )

    try:
        ids = await to_thread.run_sync(tool_repo.create_tool_nodes, project_id, rows)
    except Exception:
        log.exception(
            "bulk default tool insert failed for %s; retrying one by one", agent_type.slug
        )
    else:
        return [node(i, r, p[1]) for i, r, p in zip(ids, rows, planned, strict=True)]

    tools: list[ToolNode] = []

    async def one(row: dict, preset: ToolPreset, tool_type: ToolType) -> None:
        try:
            node_id = await _provision_tool_node(
                project_id,
                tool_type,
                preset.name,
                dict(preset.config),
                {},
                position_x=row["position_x"],
                position_y=row["position_y"],
                tool_repo=tool_repo,
                verify=False,
            )
            tools.append(node(node_id, row, tool_type))
        except Exception:
            log.exception(
                "default preset %s failed for agent type %s", preset.slug, agent_type.slug
            )

    async with anyio.create_task_group() as tg:
        for row, (preset, tool_type, _, _) in zip(rows, planned, strict=True):
            tg.start_soon(one, row, preset, tool_type)
    return tools


def _verify_in_background(tools: list[ToolNode], tool_repo: ToolRepo) -> None:
    # Verify hits the network (MCP handshake, API ping) and was gating the
    # response. Rows sit at 'pending' until it lands; the canvas poll shows it.
    if not tools:
        return
    task = asyncio.create_task(_verify_defaults(tools, tool_repo))
    _background.add(task)
    task.add_done_callback(_background.discard)


# Strong refs so the loop doesn't GC a running verify.
_background: set[asyncio.Task] = set()


async def _verify_defaults(tools: list[ToolNode], tool_repo: ToolRepo) -> None:
    """Verify fresh default tool nodes: no re-reads, one status PATCH per outcome.

    Defaults carry no secrets, so there are no keys to read. MCP verify goes
    through the pool, so the handshake is shared with later turns.
    """
    groups: dict[tuple[str, str | None], list[str]] = {}

    async def one(node: ToolNode) -> None:
        try:
            status_, detail, found = await _check_tool_node(node, [])
            if found is not None:
                config = {**node.config, "discovered_tools": found}
                await to_thread.run_sync(lambda: tool_repo.set_node_config(node.id, config))
        except Exception:
            log.exception("background verify failed for tool node %s", node.id)
            # Never leave it 'pending': the canvas spins its agent until it isn't.
            status_, detail = "error", "Verification failed."
        groups.setdefault((status_, detail), []).append(node.id)

    async def write(outcome: tuple[str, str | None], ids: list[str]) -> None:
        try:
            await to_thread.run_sync(lambda: tool_repo.set_nodes_status(ids, *outcome))
            return
        except Exception:
            log.exception("batch status write failed for %s; retrying one by one", ids)
        for node_id in ids:
            try:
                await to_thread.run_sync(lambda i=node_id: tool_repo.set_node_status(i, *outcome))
            except Exception:
                log.exception("could not write status for tool node %s", node_id)

    token = POOLED_VERIFY.set(True)
    try:
        async with anyio.create_task_group() as tg:
            for node in tools:
                tg.start_soon(one, node)
    finally:
        POOLED_VERIFY.reset(token)
    async with anyio.create_task_group() as tg:
        for outcome, ids in groups.items():
            tg.start_soon(write, outcome, ids)


async def _check_tool_node(
    node: ToolNode, keys: list[str]
) -> tuple[str, str | None, list[str] | None]:
    """spec.verify one node: (status, detail, discovered_tools). Writes nothing."""
    spec = get_spec(node.tool_slug)
    if spec is None:
        return "error", f"Unknown tool '{node.tool_slug}'", None

    try:
        secrets = await to_thread.run_sync(lambda: load_node_secrets(node.id, keys))
    except RuntimeError:
        return "error", "Secrets are unavailable", None

    secrets = {**platform_secrets(node.tool_slug), **secrets}
    try:
        secrets = await with_access_token(node.tool_slug, node.id, secrets)
    except TokenExchangeError:
        # Revoked at Google. Never retry, let the node go to error.
        return "error", "Access was revoked. Reconnect the node.", None

    result = await spec.verify(ToolContext(node.id, node.name, node.config, secrets))
    return ("ready" if result.ok else "error"), result.detail, result.discovered_tools


async def _verify_tool_node(node_id: str, tool_repo: ToolRepo) -> None:
    """Run the node's spec.verify and persist the outcome. Failures write status, never raise."""
    node = await to_thread.run_sync(tool_repo.get_tool_node, node_id)
    if node is None:
        return

    keys: list[str] = []
    if get_spec(node.tool_slug) is not None:
        keys = await to_thread.run_sync(tool_repo.secret_keys, node.id)
    status_, detail, found = await _check_tool_node(node, keys)

    if found is not None:
        merged_config = dict(node.config)
        merged_config["discovered_tools"] = found
        await to_thread.run_sync(lambda: tool_repo.set_node_config(node.id, merged_config))

    await to_thread.run_sync(lambda: tool_repo.set_node_status(node.id, status_, detail))


@router.get("/tool-types", response_model=list[ToolTypeResponse])
async def list_tool_types(tool_repo: ToolRepo) -> list[ToolTypeResponse]:
    """The palette of tool templates a node can be provisioned from."""
    types = await to_thread.run_sync(tool_repo.list_tool_types)
    return [ToolTypeResponse.of(t) for t in types]


@router.get("/models", response_model=list[str])
async def list_available_models() -> list[str]:
    """Model names the configured provider serves, for a per-node model picker."""
    try:
        return await list_models()
    except ModelsUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The model catalogue is unavailable.",
        ) from exc


@router.get("/tool-presets", response_model=list[ToolPresetResponse])
async def list_tool_presets(tool_repo: ToolRepo) -> list[ToolPresetResponse]:
    """The library of ready-to-instantiate tools and skills."""
    presets = await to_thread.run_sync(tool_repo.list_presets)
    return [ToolPresetResponse.of(p) for p in presets]


@router.post(
    "/projects/{project_id}/nodes/{node_id}/verify",
    response_model=ToolNodeResponse,
)
async def verify_tool_node(
    project_id: UUID,
    node_id: UUID,
    tool_repo: ToolRepo,
) -> ToolNodeResponse:
    """Re-run a tool node's connectivity check and persist the result."""
    node = await to_thread.run_sync(tool_repo.get_tool_node, str(node_id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool node not found")

    await _verify_tool_node(str(node_id), tool_repo)

    updated = await to_thread.run_sync(tool_repo.get_tool_node, str(node_id))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool node not found")
    secrets_set = await to_thread.run_sync(tool_repo.secret_keys, str(node_id))
    return ToolNodeResponse.of(updated, secrets_set)


@router.get("/projects/{project_id}/nodes/{node_id}/tool-calls")
async def list_tool_calls(
    project_id: UUID,
    node_id: UUID,
    tool_repo: ToolRepo,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """The audit log of calls made against one tool node."""
    node = await to_thread.run_sync(tool_repo.get_tool_node, str(node_id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool node not found")
    return await to_thread.run_sync(lambda: tool_repo.list_calls(str(node_id), limit))


# -- EDGES ---------------------------------------------------------------------


# Each edge kind runs between one pair of node kinds, source first.
_EDGE_ENDPOINTS: dict[str, tuple[str, str]] = {
    "context": ("agent", "agent"),
    "tool": ("tool", "agent"),
    "environment": ("environment", "agent"),
}


class CreateEdgeRequest(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    kind: Literal["context", "tool", "environment"] = "context"


class EdgeResponse(BaseModel):
    id: UUID
    source_node_id: UUID
    target_node_id: UUID
    kind: str
    is_stale: bool
    # 0 when fresh, null when never summarised.
    messages_behind: int | None = None
    summarised_through_seq: int | None = None
    summary_updated_at: datetime | None = None

    @classmethod
    def of(cls, e: Edge, is_stale: bool, messages_behind: int | None = None) -> "EdgeResponse":
        return cls(
            id=e.id,
            source_node_id=e.source_node_id,
            target_node_id=e.target_node_id,
            kind=e.kind,
            is_stale=is_stale,
            messages_behind=messages_behind,
            summarised_through_seq=e.summarised_through_seq,
            summary_updated_at=e.summary_updated_at,
        )


@router.post(
    "/projects/{project_id}/edges", response_model=EdgeResponse, status_code=status.HTTP_201_CREATED
)
async def create_edge(
    project_id: UUID,
    req: CreateEdgeRequest,
    repo: ProjectRepo,
) -> EdgeResponse:
    """Create an edge between two nodes on the canvas."""
    node_ids = [str(req.source_node_id), str(req.target_node_id)]
    project, found = await asyncio.gather(
        to_thread.run_sync(repo.get_project, str(project_id)),
        to_thread.run_sync(repo.node_kinds, node_ids),
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Both endpoints must be in this project, then check the kind pair this
    # edge kind allows.
    required_kinds = _EDGE_ENDPOINTS[req.kind]
    actual_kinds: list[str] = []
    for node_id in node_ids:
        info = found.get(node_id)
        if info is None or info[0] != str(project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        actual_kinds.append(info[1])

    if tuple(actual_kinds) != required_kinds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{req.kind}' edges run {required_kinds[0]} to {required_kinds[1]}, "
                f"not {actual_kinds[0]} to {actual_kinds[1]}"
            ),
        )

    # Create the edge, mapping duplicate and invalid endpoint errors.
    try:
        edge = await to_thread.run_sync(
            lambda: repo.create_edge(
                str(req.source_node_id),
                str(req.target_node_id),
                req.kind,
            )
        )
    except DuplicateEdge as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That edge already exists",
        ) from exc
    except APIError as exc:
        if exc.code == "23514":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid edge: a node cannot be its own source and target"
                "nodes must belong to this project",
            ) from exc
        raise

    # A new edge is always stale.
    return EdgeResponse.of(edge, is_stale=True)


@router.get("/projects/{project_id}/edges", response_model=list[EdgeResponse])
async def list_edges(project_id: UUID, repo: ProjectRepo) -> list[EdgeResponse]:
    """List the edges on a project's canvas."""
    project, edges = await asyncio.gather(
        to_thread.run_sync(repo.get_project, str(project_id)),
        to_thread.run_sync(repo.list_edges, str(project_id)),
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Heads only for summarised context edges: one conversation lookup for all
    # sources, then one concurrent seq read each.
    sources = list(
        {
            e.source_node_id
            for e in edges
            if e.kind == "context" and e.summarised_through_seq is not None
        }
    )
    heads: dict[str, int] = {}
    if sources:
        conv_ids = await to_thread.run_sync(repo.conversation_ids_for_nodes, sources)
        seqs = await asyncio.gather(
            *(to_thread.run_sync(repo.conversation_head_seq, c) for c in conv_ids.values())
        )
        heads = dict(zip(conv_ids, seqs, strict=True))

    out = []
    for e in edges:
        if e.kind != "context":
            out.append(EdgeResponse.of(e, is_stale=False, messages_behind=None))
        elif e.summarised_through_seq is None:
            # Never summarised: stale, with no meaningful gap.
            out.append(EdgeResponse.of(e, is_stale=True, messages_behind=None))
        else:
            behind = max(0, heads.get(e.source_node_id, 0) - e.summarised_through_seq)
            out.append(EdgeResponse.of(e, is_stale=behind > 0, messages_behind=behind))
    return out


@router.delete("/projects/{project_id}/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(project_id: UUID, edge_id: UUID, repo: ProjectRepo) -> None:
    """Remove an edge from the canvas."""
    # Check the project before deleting.
    project = await to_thread.run_sync(repo.get_project, str(project_id))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    deleted = await to_thread.run_sync(repo.delete_edge, str(edge_id))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")


# -- STALE CONTEXT CHECK ----------------------------------------------------------------


@router.post("/projects/{project_id}/edges/{edge_id}/refresh", response_model=EdgeResponse)
async def refresh_edge_summary(project_id: UUID, edge_id: UUID, repo: ProjectRepo) -> EdgeResponse:
    """Regenerate a context edge's summary from its source conversation."""
    project, edge = await asyncio.gather(
        to_thread.run_sync(repo.get_project, str(project_id)),
        to_thread.run_sync(repo.get_edge, str(edge_id)),
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")
    if edge.kind != "context":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only context edges carry a summary",
        )

    updated = await refresh_edge(repo, edge)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Summary could not be stored",
        )
    # Re-read the head: a turn can complete while the summariser runs.
    head = await to_thread.run_sync(repo.get_conversation_head, updated.source_node_id)
    behind = max(0, head - (updated.summarised_through_seq or 0))
    return EdgeResponse.of(updated, is_stale=behind > 0, messages_behind=behind)
