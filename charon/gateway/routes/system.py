"""
charon/gateway/routes/system.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Gateway Systemd Control Endpoints.
Provides API routing for systemd registry, status monitoring, service control, and file editing.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from charon.core.services import systemd as systemd_service

logger = logging.getLogger("Charon.Gateway.RoutesSystem")

router = APIRouter(prefix="/v1/system", tags=["System Control"])


class RegisteredUnitRegisterRequest(BaseModel):
    name: str = Field(..., description="Systemd unit service name")
    scope: str = Field("user", description="Execution space: 'user' or 'system'")


class UnitStatusModel(BaseModel):
    name: str = Field(..., description="Systemd unit service name")
    active: bool = Field(..., description="Whether unit active_state is 'active'")
    subState: str = Field(..., description="Detailed sub-state (e.g. running, dead, exited)")
    scope: str = Field(..., description="Target execution space: 'user' or 'system'")
    loadState: str = Field(default="loaded", description="Load state of the unit")
    description: Optional[str] = Field(default="", description="Unit description header")
    uptime: Optional[str] = Field(default="N/A", description="Human-readable unit active duration")


class SystemUnitsResponse(BaseModel):
    status: str = "success"
    count: int
    units: List[UnitStatusModel]


class FileContentPayload(BaseModel):
    content: str = Field(..., description="Raw text content of the unit file")


@router.get("/registered-units", response_model=Dict[str, Any])
async def list_registered_units():
    """Retrieves all service units registered in Charon settings."""
    units = systemd_service.get_registered_units()
    return {"status": "success", "count": len(units), "registered_units": units}


@router.post("/registered-units", response_model=Dict[str, Any])
async def register_unit(payload: RegisteredUnitRegisterRequest):
    """Registers a new service unit to the monitored settings list."""
    try:
        updated = systemd_service.register_unit(payload.name, payload.scope)
        return {"status": "success", "registered_units": updated}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.delete("/registered-units/{unit_name}", response_model=Dict[str, Any])
async def unregister_unit(unit_name: str):
    """Removes a service unit from the monitored settings list."""
    updated = systemd_service.unregister_unit(unit_name)
    return {"status": "success", "registered_units": updated}


@router.get("/units", response_model=SystemUnitsResponse)
async def list_monitored_system_units():
    """Retrieves status for all registered units of interest."""
    try:
        units_data = await systemd_service.get_monitored_units_status()
        units = [UnitStatusModel(**u) for u in units_data]
        return SystemUnitsResponse(status="success", count=len(units), units=units)
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(err))
    except Exception as err:
        logger.error(f"[System API] Error listing systemd units: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query systemd units: {str(err)}",
        )


@router.post("/units/{unit_name}/{action}", response_model=Dict[str, Any])
async def control_system_unit(
    unit_name: str,
    action: str,
    scope: str = Query("user", description="Execution space ('user' or 'system')")
):
    """Executes start, stop, restart, or reload operations on a unit."""
    try:
        await systemd_service.control_unit(unit_name, action.lower(), scope.lower())
        logger.info(f"[System API] Executed 'systemctl {action} {unit_name}' (scope={scope})")
        return {
            "status": "success",
            "unit": unit_name,
            "action": action,
            "scope": scope,
            "message": f"Successfully executed '{action}' on unit '{unit_name}'.",
        }
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"[System API] Service action failed: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {action} service '{unit_name}': {str(err)}",
        )


@router.get("/units/{unit_name}/content", response_model=Dict[str, Any])
async def get_unit_file(
    unit_name: str,
    scope: str = Query("user", description="Execution space ('user' or 'system')")
):
    """Fetches raw contents of a service unit file for editing."""
    try:
        content = await systemd_service.get_unit_file_content(unit_name, scope.lower())
        return {"status": "success", "unit": unit_name, "content": content}
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.put("/units/{unit_name}/content", response_model=Dict[str, Any])
async def update_unit_file(
    unit_name: str,
    payload: FileContentPayload,
    scope: str = Query("user", description="Execution space ('user' or 'system')")
):
    """Saves updated service unit file contents and triggers systemctl daemon-reload."""
    try:
        await systemd_service.update_unit_file_content(unit_name, payload.content, scope.lower())
        return {
            "status": "success",
            "unit": unit_name,
            "message": f"Updated unit file for '{unit_name}' and reloaded daemon.",
        }
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))