"""RBAC Middleware for Home Assistant."""
import logging
import os
import shutil
from typing import Any, Dict, Optional
from datetime import datetime

import yaml

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.template import Template
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = "rbac"

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


class RBACConfigURLSensor(SensorEntity):
    """Sensor for RBAC configuration URL."""
    
    def __init__(self, base_url: str = ""):
        """Initialize the sensor."""
        self._attr_name = "RBAC Configuration URL"
        self._attr_unique_id = f"{DOMAIN}_config_url"
        self._attr_icon = "mdi:web"
        self._attr_device_class = "url"
        self._attr_native_value = f"{base_url}/api/rbac/static/config.html" if base_url else "/api/rbac/static/config.html"


ACCESS_CONTROL_FILE = "access_control.yaml"
DENY_LOG_FILE = "deny_list.log"


def _storage_path(hass: HomeAssistant, filename: str) -> str:
    """Path of a writable RBAC data file, kept outside the component folder.

    The component folder may be read-only (e.g. installed from the Nix store)
    or replaced on update (e.g. by HACS), so data lives in <config>/rbac/.
    """
    return hass.config.path(DOMAIN, filename)


def _legacy_path(hass: HomeAssistant, filename: str) -> str:
    """Path of a data file in the old location inside the component folder."""
    return os.path.join(hass.config.config_dir, "custom_components", DOMAIN, filename)


def _migrate_storage(hass: HomeAssistant) -> None:
    """Copy data files from the component folder to the storage folder once."""
    os.makedirs(hass.config.path(DOMAIN), exist_ok=True)
    for filename in (ACCESS_CONTROL_FILE, DENY_LOG_FILE):
        new_path = _storage_path(hass, filename)
        old_path = _legacy_path(hass, filename)
        if os.path.exists(new_path) or not os.path.isfile(old_path):
            continue
        try:
            # copyfile doesn't copy permissions, so a read-only source yields a writable copy
            shutil.copyfile(old_path, new_path)
            _LOGGER.info(f"Migrated {old_path} to {new_path}")
        except Exception as e:
            _LOGGER.error(f"Failed to migrate {old_path} to {new_path}: {e}")


async def _load_access_control_config(hass: HomeAssistant) -> Dict[str, Any]:
    """Load access control configuration from YAML file."""
    config_path = _storage_path(hass, ACCESS_CONTROL_FILE)

    def _load_file():
        _migrate_storage(hass)
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            _LOGGER.info(f"Access control configuration not found at {config_path}, creating default configuration")
            default_config = {
                "version": "2.0",
                "description": "RBAC Access Control Configuration",
                "enabled": True,
                "show_notifications": True,
                "send_event": False,
                "frontend_blocking_enabled": False,
                "log_deny_list": False,
                "allow_chained_actions": False,
                "last_rejection": "Never",
                "last_user_rejected": "None",
                "default_restrictions": {
                    "domains": {
                        "homeassistant": {
                            "hide": False,
                            "services": ["restart", "stop", "reload_config_entry", "check_config"]
                        },
                        "system_log": {
                            "hide": True,
                            "services": ["write", "clear"]
                        },
                        "hassio": {
                            "hide": True,
                            "services": ["host_reboot", "host_shutdown", "supervisor_update", "supervisor_restart"]
                        }
                    },
                    "entities": {}
                },
                "users": {},
                "roles": {
                    "admin": {"description": "Administrator with most permissions"},
                    "user": {"description": "Standard user with limited permissions"},
                    "guest": {"description": "Guest with minimal permissions"}
                }
            }
            
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False, indent=2, sort_keys=False)
            
            _LOGGER.info(f"Created default access control configuration at {config_path}")
            return default_config
        except yaml.YAMLError as e:
            _LOGGER.error(f"Invalid YAML in access control configuration: {e}")
            return {"default_access": "allow", "users": {}}
        except Exception as e:
            _LOGGER.error(f"Error loading access control configuration: {e}")
            return {"default_access": "allow", "users": {}}
    
    config = await hass.async_add_executor_job(_load_file)
    _LOGGER.info(f"Loaded access control configuration from {config_path}")
    return config


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the RBAC middleware component from configuration.yaml."""
    _LOGGER.info("Setting up RBAC Middleware from configuration.yaml")
    
    access_config = await _load_access_control_config(hass)
    
    hass.data[DOMAIN] = {
        "access_config": access_config,
        "original_async_call": None
    }
    
    hass.data[DOMAIN]["original_async_call"] = hass.services.async_call
    
    _patch_service_registry(hass)
    
    from . import services
    await services.async_setup_services(hass)
    
    await services.async_setup_static_routes(hass)
    
    _LOGGER.info("Skipping device setup for YAML-only configuration")
    
    user_count = len(access_config.get("users", {}))
    _LOGGER.info(f"RBAC Middleware initialized successfully with {user_count} configured users")
    
    from .services import RBACConfigView, RBACUsersView, RBACDomainsView, RBACEntitiesView, RBACAreasView, RBACServicesView, RBACCurrentUserView, RBACSensorsView, RBACDenyLogView, RBACTemplateEvaluateView, RBACFrontendBlockingView, RBACYamlEditorView
    
    hass.http.register_view(RBACConfigView())
    hass.http.register_view(RBACUsersView())
    hass.http.register_view(RBACDomainsView())
    hass.http.register_view(RBACEntitiesView())
    hass.http.register_view(RBACAreasView())
    hass.http.register_view(RBACServicesView())
    hass.http.register_view(RBACCurrentUserView())
    hass.http.register_view(RBACSensorsView())
    hass.http.register_view(RBACDenyLogView())
    hass.http.register_view(RBACTemplateEvaluateView())
    hass.http.register_view(RBACFrontendBlockingView())
    hass.http.register_view(RBACYamlEditorView())
    
    _LOGGER.info("Registered RBAC API endpoints")
    
    await _register_sidebar_panel(hass)
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    """Set up the RBAC middleware component from a config entry."""
    _LOGGER.info("Setting up RBAC Middleware from config entry")
    
    config_data = entry.data if entry.data else {}
    
    await _setup_rbac_device(hass, entry)
    
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return await async_setup(hass, config_data)


async def async_update_options(hass: HomeAssistant, entry) -> None:
    """Update options."""
    _LOGGER.info("RBAC options updated")
    
    should_show_panel = entry.options.get("show_sidebar_panel", True)
    
    if should_show_panel:
        await _register_sidebar_panel(hass)
    else:
        try:
            from homeassistant.components.frontend import async_remove_panel
            await async_remove_panel(hass, "rbac-config")
            _LOGGER.info("RBAC sidebar panel removed due to option change")
        except Exception as e:
            _LOGGER.debug(f"Could not remove RBAC sidebar panel: {e}")


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    """Unload RBAC config entry."""
    _LOGGER.info("Unloading RBAC Middleware")
    
    try:
        from homeassistant.components.frontend import async_remove_panel
        await async_remove_panel(hass, "rbac-config")
        _LOGGER.info("Successfully removed RBAC sidebar panel")
    except Exception as e:
        _LOGGER.debug(f"Could not remove RBAC sidebar panel: {e}")
    
    try:
        await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    except Exception as e:
        _LOGGER.debug(f"Could not unload sensor platform: {e}")
    
    return True


async def _setup_rbac_device(hass: HomeAssistant, config_entry):
    """Set up RBAC device and sensors."""
    _LOGGER.info("Setting up RBAC device and sensors...")
    
    try:
        from homeassistant.helpers import device_registry as dr, entity_registry as er
        
        device_reg = dr.async_get(hass)
        device = device_reg.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, "rbac_middleware")},
            name="RBAC Middleware",
            manufacturer="Home Assistant",
            model="RBAC Integration",
            sw_version="1.0.0",
        )
        
        hass.data[DOMAIN]["device_id"] = device.id
        
        from homeassistant.config_entries import ConfigEntry
        await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor"])
        
        _LOGGER.info(f"Created RBAC device {device.id} and loaded sensor platform")
        
    except Exception as e:
        _LOGGER.warning(f"Could not create device/sensors properly: {e}")


def _patch_service_registry(hass: HomeAssistant):
    """Patch the service registry to intercept service calls."""
    original_registry = hass.services
    
    class RestrictedServiceRegistry:
        def __init__(self, original_registry, hass):
            self._original = original_registry
            self._hass = hass
            
        def __getattr__(self, name):
            return getattr(self._original, name)
            
        async def async_call(self, domain, service, service_data=None, blocking=False, context=None, **kwargs):
            """Intercept service calls for RBAC enforcement."""
            try:
                access_config = self._hass.data.get(DOMAIN, {}).get("access_config", {})
                allow_chained_actions = access_config.get("allow_chained_actions", False)
                
                if allow_chained_actions and context:
                    if 'allowed_contexts' not in self._hass.data[DOMAIN]:
                        self._hass.data[DOMAIN]['allowed_contexts'] = set()
                    
                    allowed_contexts = self._hass.data[DOMAIN]['allowed_contexts']
                    
                    context_chain = []
                    if hasattr(context, 'id') and context.id:
                        context_chain.append(context.id)
                    if hasattr(context, 'parent_id') and context.parent_id:
                        context_chain.append(context.parent_id)
                    
                    for ctx_id in context_chain:
                        if ctx_id in allowed_contexts:
                            _LOGGER.debug(f"Allowing chained action {domain}.{service} from allowed context {ctx_id}")
                            return await self._original.async_call(domain, service, service_data, blocking, context, **kwargs)
                
                excluded_domains = ['http', 'auth', 'system_log', 'persistent_notification']
                if domain in excluded_domains:
                    _LOGGER.warning(f"Skipping RBAC enforcement for {domain}.{service} (excluded domain)")
                    return await self._original.async_call(domain, service, service_data, blocking, context, **kwargs)
                
                user = None
                user_id = None
                
                if context and hasattr(context, 'user_id') and context.user_id:
                    user = await self._hass.auth.async_get_user(context.user_id)
                    user_id = context.user_id
                    _LOGGER.warning(f"Got user from context: {user_id} ({user.name if user else 'Unknown'})")
                else:
                    user_id = None
                
                if user_id and await _is_builtin_ha_user(user_id, self._hass):
                    _LOGGER.warning(f"Skipping RBAC enforcement for built-in HA user: {user_id} ({user.name if user else 'Unknown'})")
                    return await self._original.async_call(domain, service, service_data, blocking, context, **kwargs)
                
                user_name = user.name if user else "Unknown"
                _LOGGER.warning(f"RBAC checking service call: {domain}.{service} by {user_name} (user_id: {user_id})")
                
                if not user_id or user_id == "null" or user_id is None:
                    _LOGGER.debug(f"No user context for {domain}.{service} - allowing call to proceed (likely automation/script)")
                    return await self._original.async_call(domain, service, service_data, blocking, context, **kwargs)
                
                access_config = self._hass.data[DOMAIN]["access_config"]
                
                rbac_enabled = access_config.get("enabled", True)
                
                if not rbac_enabled:
                    _LOGGER.warning(f"RBAC is disabled - allowing all service calls")
                    return await self._original.async_call(domain, service, service_data, blocking, context, **kwargs)
                
                if rbac_enabled:
                    _LOGGER.warning(f"Access config for {user_name}: {access_config}")
                    
                    access_result, reason = _check_service_access_with_reason(
                        domain, service, service_data, user_id, access_config, self._hass, kwargs.get("target")
                    )
                    
                    if not access_result and service_data and "entity_id" in service_data:
                        _LOGGER.warning(f"Access check result for {user_name}: {access_result}, reason: {reason}")
                        _LOGGER.warning(f"Service data: {service_data}")
                    
                    if not access_result:
                        if service_data and "entity_id" in service_data:
                            user_role = "unknown"
                            if user_id:
                                users = access_config.get("users", {})
                                user_config = users.get(user_id)
                                if user_config:
                                    user_role = user_config.get("role", "unknown")
                            
                            _LOGGER.warning(
                                f"Access denied: {user_name} cannot call {domain}.{service} from role '{user_role}' - {reason}"
                            )
                        else:
                            _LOGGER.debug(f"Access denied for {user_name} calling {domain}.{service} (no entity_id) - {reason}")
                        
                        if service_data and "entity_id" in service_data:
                            try:
                                from .services import _update_rejection_sensors
                                _update_rejection_sensors(hass, user_id, f"{domain}.{service}")
                            except Exception as e:
                                _LOGGER.error(f"Error updating rejection sensors: {e}")
                            
                            if access_config.get("show_notifications", True):
                                try:
                                    await self._original.async_call(
                                        "persistent_notification",
                                        "create",
                                        {
                                            "message": f"Access denied: {user_name} cannot call {domain}.{service} from role '{user_role}'",
                                            "title": "RBAC Access Denied",
                                            "notification_id": f"rbac_denied_{domain}_{service}"
                                        }
                                    )
                                except Exception as e:
                                    _LOGGER.error(f"Failed to create notification: {e}")
                                    _LOGGER.debug(f"Notification error details: {e}", exc_info=True)
                            
                            if access_config.get("send_event", False):
                                try:
                                    event_data = {
                                        "user_id": user_id,
                                        "user_name": user_name,
                                        "domain": domain,
                                        "service": service,
                                        "service_data": service_data,
                                        "reason": reason
                                    }
                                    self._hass.bus.async_fire("rbac_access_denied", event_data)
                                    _LOGGER.debug(f"Fired rbac_access_denied event: {event_data}")
                                except Exception as e:
                                    _LOGGER.error(f"Failed to send event: {e}")
                        
                        user_role = "unknown"
                        if user_id:
                            users = access_config.get("users", {})
                            user_config = users.get(user_id)
                            if user_config:
                                user_role = user_config.get("role", "unknown")
                        
                        if access_config.get("log_deny_list", False):
                            try:
                                _log_denial_to_file(self._hass, user_id or "unknown", user_name, user_role, domain, service, reason)
                            except Exception as log_error:
                                _LOGGER.error(f"Failed to log denial: {log_error}")
                        
                        raise HomeAssistantError(
                            f"Access denied: {user_name} cannot call {domain}.{service} from role '{user_role}' - {reason}"
                        )
                
                if rbac_enabled:
                    _LOGGER.debug(f"Service call allowed: {domain}.{service} by {user_name}")
                else:
                    _LOGGER.debug(f"Service call allowed (blocking disabled): {domain}.{service} by {user_name}")
                
                context_id_added = None
                if allow_chained_actions and context:
                    if 'allowed_contexts' not in self._hass.data[DOMAIN]:
                        self._hass.data[DOMAIN]['allowed_contexts'] = set()
                    
                    if hasattr(context, 'id') and context.id:
                        self._hass.data[DOMAIN]['allowed_contexts'].add(context.id)
                        context_id_added = context.id
                        _LOGGER.debug(f"Added context {context.id} to allowed contexts for {domain}.{service}")
                
                try:
                    return await self._original.async_call(domain, service, service_data, blocking, context, **kwargs)
                finally:
                    if context_id_added:
                        try:
                            self._hass.data[DOMAIN]['allowed_contexts'].discard(context_id_added)
                            _LOGGER.debug(f"Removed context {context_id_added} from allowed contexts for {domain}.{service}")
                        except (KeyError, AttributeError):
                            pass
                
            except HomeAssistantError:
                raise
            except Exception as e:
                _LOGGER.warning(
                    f"RBAC error for {domain}.{service}: {e}. Allowing service call to proceed."
                )
                _LOGGER.debug(f"RBAC error details: {e}", exc_info=True)
                
                try:
                    if service_data and isinstance(service_data, dict):
                        cleaned_data = service_data.copy()
                        for key in ['rgb_color', 'xy_color', 'hs_color', 'color_temp']:
                            if key in cleaned_data and not isinstance(cleaned_data[key], (list, tuple)):
                                _LOGGER.debug(f"Removing invalid {key} from service_data: {cleaned_data[key]}")
                                del cleaned_data[key]
                        service_data = cleaned_data
                except Exception as cleanup_error:
                    _LOGGER.debug(f"Failed to clean service_data: {cleanup_error}")
                
                return await self._original.async_call(domain, service, service_data, blocking, context, **kwargs)
    
    hass.services = RestrictedServiceRegistry(original_registry, hass)
    _LOGGER.warning("RBAC service registry patching applied successfully")
    
    _patch_service_list(hass)
    




def _patch_service_list(hass: HomeAssistant):
    """Patch the service registry to filter restricted services from service lists."""
    original_registry = hass.services
    
    class FilteredServiceRegistry:
        def __init__(self, original_registry, hass):
            self._original = original_registry
            self._hass = hass
            
        def __getattr__(self, name):
            return getattr(self._original, name)
            
        async def async_call(self, domain, service, service_data=None, blocking=False, context=None, **kwargs):
            """Intercept service calls for RBAC enforcement."""
            return await self._original.async_call(domain, service, service_data, blocking, context, **kwargs)
        
        def services_for_domain(self, domain):
            """Get services for a domain, filtering restricted services for users."""
            try:
                user_id = None
                try:
                    from homeassistant.core import Context
                    context = Context()
                    if hasattr(context, 'user_id') and context.user_id:
                        user_id = context.user_id
                except:
                    pass
                
                if not user_id:
                    return self._original.services_for_domain(domain)
                
                all_services = self._original.services_for_domain(domain)
                
                filtered_services = {}
                for service_name, service_info in all_services.items():
                    if not _is_service_restricted_for_user(domain, service_name, user_id, hass):
                        filtered_services[service_name] = service_info
                    else:
                        _LOGGER.debug(f"Filtering out restricted service {domain}.{service_name} for user {user_id}")
                
                return filtered_services
            except Exception as e:
                _LOGGER.warning(f"RBAC error in services.services_for_domain({domain}): {e}. Showing all services to prevent lockout.")
                _LOGGER.debug(f"RBAC error details: {e}", exc_info=True)
                return self._original.services_for_domain(domain)
        
        def async_services(self):
            """Get all services, filtering restricted services for users."""
            try:
                user_id = None
                try:
                    from homeassistant.core import Context
                    context = Context()
                    if hasattr(context, 'user_id') and context.user_id:
                        user_id = context.user_id
                except:
                    pass
                
                if not user_id:
                    return self._original.async_services()
                
                all_services = self._original.async_services()
                
                filtered_services = {}
                for domain, services in all_services.items():
                    filtered_domain_services = {}
                    for service_name, service_info in services.items():
                        if not _is_service_restricted_for_user(domain, service_name, user_id, hass):
                            filtered_domain_services[service_name] = service_info
                        else:
                            _LOGGER.debug(f"Filtering out restricted service {domain}.{service_name} for user {user_id}")
                    
                    if filtered_domain_services:
                        filtered_services[domain] = filtered_domain_services
                
                return filtered_services
            except Exception as e:
                _LOGGER.warning(f"RBAC error in services.async_services(): {e}. Showing all services to prevent lockout.")
                _LOGGER.debug(f"RBAC error details: {e}", exc_info=True)
                return self._original.async_services()
    
    hass.services = FilteredServiceRegistry(original_registry, hass)


def _is_service_restricted_for_user(domain: str, service: str, user_id: str, hass: HomeAssistant) -> bool:
    """Check if a service is restricted for a specific user."""
    if DOMAIN not in hass.data:
        return False
    
    access_config = hass.data[DOMAIN].get("access_config", {})
    
    users = access_config.get("users", {})
    user_config = users.get(user_id)
    
    if not user_config:
        default_restrictions = access_config.get("default_restrictions", {})
        if default_restrictions:
            default_domains = default_restrictions.get("domains", {})
            if domain in default_domains:
                domain_config = default_domains[domain]
                if domain_config.get("hide", False):
                    return True
                default_services = domain_config.get("services", [])
                if service in default_services:
                    return True
        return False
    
    restrictions = user_config.get("restrictions", {})
    domains = restrictions.get("domains", {})
    
    if domain in domains:
        domain_config = domains[domain]
        if domain_config.get("hide", False):
            return True
        services = domain_config.get("services", [])
        if service in services:
            return True
    
    return False


async def _is_builtin_ha_user(user_id: str, hass: HomeAssistant = None) -> bool:
    """Check if a user is a built-in Home Assistant user that should be excluded from RBAC.
    
    Uses `hass.auth` to look up the user and check the `system_generated` flag.
    """
    if not hass:
        # Fallback to name-based checking if hass is not available
        return False
    
    user = await hass.auth.async_get_user(user_id)

    if user is None:
        return False
    
    return bool(user.system_generated)


def _get_entity_area_id(hass: HomeAssistant, entity_id: str) -> Optional[str]:
    """Get the area of an entity: its own area, falling back to its device's area."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id:
        return entry.area_id
    if entry.device_id:
        device = dr.async_get(hass).async_get(entry.device_id)
        if device:
            return device.area_id
    return None


def _as_set(value: Any) -> set:
    """Normalize a single value or list from a service target into a set."""
    if not value:
        return set()
    if isinstance(value, str):
        return {v.strip() for v in value.split(",") if v.strip()}
    if isinstance(value, (list, tuple, set)):
        return {v for v in value if isinstance(v, str)}
    return set()


def _resolve_target_entities(
    hass: HomeAssistant,
    domain: str,
    service: str,
    service_data: Optional[Dict[str, Any]],
    target: Optional[Dict[str, Any]] = None
) -> set:
    """Resolve all entities targeted by a service call.

    Expands entity_id, area_id, device_id, floor_id and label_id targets
    from both service_data and the target kwarg into entity IDs.
    """
    from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

    data = {}
    if isinstance(service_data, dict):
        data.update(service_data)
    if isinstance(target, dict):
        data.update(target)

    entity_ids = _as_set(data.get("entity_id"))
    if "all" in entity_ids:
        entity_ids.discard("all")
        entity_ids.update(hass.states.async_entity_ids(domain))

    # Scripts can be called directly as script.<script_name>
    if domain == "script" and hass.states.get(f"script.{service}") is not None:
        entity_ids.add(f"script.{service}")

    area_ids = _as_set(data.get("area_id"))
    device_ids = _as_set(data.get("device_id"))
    floor_ids = _as_set(data.get("floor_id"))
    label_ids = _as_set(data.get("label_id"))

    if not (area_ids or device_ids or floor_ids or label_ids):
        return entity_ids

    area_reg = ar.async_get(hass)
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    if floor_ids or label_ids:
        for area in area_reg.async_list_areas():
            if getattr(area, "floor_id", None) in floor_ids or label_ids & set(getattr(area, "labels", ()) or ()):
                area_ids.add(area.id)

    if label_ids:
        for device in device_reg.devices.values():
            if label_ids & set(getattr(device, "labels", ()) or ()):
                device_ids.add(device.id)

    for entry in entity_reg.entities.values():
        if entry.entity_category is not None or entry.hidden_by is not None:
            # HA skips config/diagnostic and hidden entities when expanding area/device targets
            if not (label_ids & set(getattr(entry, "labels", ()) or ())):
                continue
        if entry.domain != domain and domain not in ("homeassistant",):
            continue
        if label_ids & set(getattr(entry, "labels", ()) or ()):
            entity_ids.add(entry.entity_id)
        elif entry.device_id in device_ids:
            entity_ids.add(entry.entity_id)
        elif _get_entity_area_id(hass, entry.entity_id) in area_ids:
            entity_ids.add(entry.entity_id)

    return entity_ids


def _rule_decision(rule_config: Any, service: str) -> Optional[bool]:
    """Evaluate a single allow/block rule. Returns True/False, or None if the rule doesn't decide."""
    if not isinstance(rule_config, dict):
        return False
    rule_services = rule_config.get("services", []) or []
    if rule_config.get("allow", False):
        return not rule_services or service in rule_services
    if not rule_services or service in rule_services:
        return False
    return None


def _check_area_access(
    hass: HomeAssistant,
    domain: str,
    service: str,
    service_data: Optional[Dict[str, Any]],
    target: Optional[Dict[str, Any]],
    permissions: Dict[str, Any],
    default_restrictions: Dict[str, Any],
    user_role: str
) -> Optional[tuple[bool, str]]:
    """Check role area (room) permissions for every entity targeted by a call.

    Precedence per entity: role entity rule > role area rule. Returns a decision
    only if any entity is denied or all entities are allowed; otherwise None so
    domain rules and Allow/Deny All apply.
    """
    role_areas = permissions.get("areas", {}) or {}
    if not role_areas:
        return None

    entity_ids = _resolve_target_entities(hass, domain, service, service_data, target)
    if not entity_ids:
        return None

    role_entities = permissions.get("entities", {}) or {}
    default_entities = default_restrictions.get("entities", {}) or {}

    all_allowed = True
    allowed_reason = None
    for eid in sorted(entity_ids):
        if eid in role_entities:
            decision = _rule_decision(role_entities[eid], service)
            if decision is False:
                return False, f"entity {eid} service {service} blocked by role {user_role}"
            if decision is True:
                continue
        elif eid in default_entities and _rule_decision(default_entities[eid], service) is False:
            return False, f"entity {eid} service {service} blocked by default restrictions"

        area_id = _get_entity_area_id(hass, eid)
        if area_id is None or area_id not in role_areas:
            all_allowed = False
            continue

        decision = _rule_decision(role_areas[area_id], service)
        if decision is False:
            return False, f"entity {eid} in area {area_id}: service {service} blocked by role {user_role}"
        if decision is None:
            all_allowed = False
        else:
            allowed_reason = f"area {area_id} service {service} allowed by role {user_role}"

    if all_allowed and allowed_reason:
        return True, allowed_reason
    return None


def _check_service_access_with_reason(
    domain: str,
    service: str,
    service_data: Optional[Dict[str, Any]],
    user_id: Optional[str],
    access_config: Dict[str, Any],
    hass: HomeAssistant = None,
    target: Optional[Dict[str, Any]] = None
) -> tuple[bool, str]:
    """Check if a user has access to a specific service call with detailed reason."""
    
    if not user_id or user_id == "null" or user_id is None:
        return True, "system call (no user_id)"
    
    users = access_config.get("users", {})
    user_config = users.get(user_id)
    
    if not user_config:
        _LOGGER.warning(f"User {user_id} not in config, checking default restrictions")
        default_restrictions = access_config.get("default_restrictions", {})
        _LOGGER.warning(f"Default restrictions: {default_restrictions}")
        if default_restrictions:
            default_domains = default_restrictions.get("domains", {})
            _LOGGER.warning(f"Checking domain {domain} against default domains: {default_domains}")
            if domain in default_domains:
                domain_config = default_domains[domain]
                _LOGGER.warning(f"Found domain {domain} config: {domain_config}")
                default_services = domain_config.get("services", [])
                if not default_services:
                    _LOGGER.warning(f"Domain {domain} blocks all services")
                    return False, f"domain {domain} blocked by default"
                elif service in default_services:
                    return False, f"service {domain}.{service} blocked by default"
            
            if service_data and "entity_id" in service_data:
                entity_id = service_data["entity_id"]
                if isinstance(entity_id, list):
                    for eid in entity_id:
                        default_entities = default_restrictions.get("entities", {})
                        if eid in default_entities:
                            entity_config = default_entities[eid]
                            default_entity_services = entity_config.get("services", [])
                            if not default_entity_services:
                                return False, f"entity {eid} blocked by default"
                            elif service in default_entity_services:
                                return False, f"entity {eid} service {service} blocked by default"
                else:
                    default_entities = default_restrictions.get("entities", {})
                    if entity_id in default_entities:
                        entity_config = default_entities[entity_id]
                        default_entity_services = entity_config.get("services", [])
                        if not default_entity_services:
                            return False, f"entity {entity_id} blocked by default"
                        elif service in default_entity_services:
                            return False, f"entity {entity_id} service {service} blocked by default"
        
        return True, f"no default restrictions"
    
    user_role = user_config.get("role", "unknown")
    
    roles = access_config.get("roles", {})
    role_config = roles.get(user_role, {})
    
    if role_config and hass:
        template_str = role_config.get("template")
        fallback_role = role_config.get("fallbackRole")
        
        if template_str and fallback_role:
            try:
                template = Template(template_str, hass)
                
                user_person_entity = None
                try:
                    for state in hass.states.async_all():
                        if state.domain == "person" and state.attributes.get("user_id") == user_id:
                            user_person_entity = state.entity_id
                            break
                except Exception as e:
                    _LOGGER.debug(f"Could not find person entity for user {user_id}: {e}")
                
                template_context = {}
                if user_person_entity:
                    template_context['current_user_str'] = user_person_entity
                
                result = template.async_render(template_context, parse_result=False)
                
                template_result = bool(result) if result not in [None, "", "False", "false", "0"] else False
                
                _LOGGER.debug(f"Template for role {user_role} evaluated to: {template_result} (raw: {result})")
                
                if not template_result:
                    _LOGGER.info(f"Template for role {user_role} evaluated to false, switching to fallback role: {fallback_role}")
                    user_role = fallback_role
                    role_config = roles.get(user_role, {})
                    
                    if not role_config:
                        _LOGGER.warning(f"Fallback role {fallback_role} not found in configuration")
                        return True, f"fallback role {fallback_role} not found"
            except Exception as e:
                _LOGGER.error(f"Error evaluating template for role {user_role}: {e}")
                _LOGGER.debug(f"Template evaluation error details: {e}", exc_info=True)
                if fallback_role:
                    _LOGGER.warning(f"Template evaluation failed for role {user_role}, switching to fallback role: {fallback_role}")
                    user_role = fallback_role
                    role_config = roles.get(user_role, {})
                    
                    if not role_config:
                        _LOGGER.warning(f"Fallback role {fallback_role} not found in configuration")
                        return True, f"fallback role {fallback_role} not found"
                else:
                    _LOGGER.error(f"No fallback role defined for role {user_role}, continuing with original role")
    
    if not role_config:
        return True, f"no role configuration for {user_role}"
    
    is_admin_role = role_config.get("admin", False)
    if is_admin_role:
        return True, f"admin role {user_role} has full access"
    
    deny_all = role_config.get("deny_all", False)
    
    default_restrictions = access_config.get("default_restrictions", {})
    permissions = role_config.get("permissions", {})
    if service_data and "entity_id" in service_data:
        entity_id = service_data["entity_id"]
        if isinstance(entity_id, list):
            for eid in entity_id:
                # Check default entity restrictions
                default_entities = default_restrictions.get("entities", {})
                if eid in default_entities:
                    default_entity_config = default_entities[eid]
                    default_entity_services = default_entity_config.get("services", [])
                    default_entity_allow = default_entity_config.get("allow", False)
                    
                    if default_entity_allow:
                        # Default allow rule: check if service is in allowed services
                        if not default_entity_services or service in default_entity_services:
                            return True, f"entity {eid} service {service} allowed by default"
                        else:
                            return False, f"entity {eid} service {service} not in default allow list"
                    else:
                        # Default block rule
                        if not default_entity_services:  # Default blocks all services
                            # Check if role allows this entity
                            role_entities = permissions.get("entities", {})
                            if eid not in role_entities:
                                return False, f"entity {eid} blocked by default restrictions"
                            role_entity_config = role_entities[eid]
                            role_entity_services = role_entity_config.get("services", [])
                            role_entity_allow = role_entity_config.get("allow", False)
                            
                            if role_entity_allow:
                                # Role allow rule: check if service is in allowed services
                                if not role_entity_services or service in role_entity_services:
                                    return True, f"entity {eid} service {service} allowed by role {user_role}"
                                else:
                                    return False, f"entity {eid} service {service} not in role allow list"
                            else:
                                # Role block rule
                                if not role_entity_services:  # Role also blocks all services
                                    return False, f"entity {eid} blocked by role {user_role}"
                                elif service not in role_entity_services:  # Service not in role's allowed list
                                    return False, f"entity {eid} service {service} not allowed by role {user_role}"
                        elif service in default_entity_services:  # Default blocks specific service
                            # Check if role allows this service
                            role_entities = permissions.get("entities", {})
                            if eid not in role_entities:
                                return False, f"entity {eid} service {service} blocked by default restrictions"
                            role_entity_config = role_entities[eid]
                            role_entity_services = role_entity_config.get("services", [])
                            role_entity_allow = role_entity_config.get("allow", False)
                            
                            if role_entity_allow:
                                # Role allow rule: check if service is in allowed services
                                if not role_entity_services or service in role_entity_services:
                                    return True, f"entity {eid} service {service} allowed by role {user_role}"
                                else:
                                    return False, f"entity {eid} service {service} not in role allow list"
                            else:
                                # Role block rule
                                if service in role_entity_services:  # Role also blocks this service
                                    return False, f"entity {eid} service {service} blocked by role {user_role}"
                
                # Check role-specific entity restrictions (always check, even if no default restrictions)
                role_entities = permissions.get("entities", {})
                if eid in role_entities:
                    role_entity_config = role_entities[eid]
                    role_entity_services = role_entity_config.get("services", [])
                    role_entity_allow = role_entity_config.get("allow", False)
                    
                    _LOGGER.warning(f"Found entity {eid} in role permissions: allow={role_entity_allow}, services={role_entity_services}")
                    
                    if role_entity_allow:
                        # Role allow rule: check if service is in allowed services
                        if not role_entity_services or service in role_entity_services:
                            return True, f"entity {eid} service {service} allowed by role {user_role}"
                        else:
                            return False, f"entity {eid} service {service} not in role allow list"
                    else:
                        # Role block rule
                        if not role_entity_services:  # Role blocks all services for this entity
                            return False, f"entity {eid} blocked by role {user_role}"
                        elif service in role_entity_services:  # Role blocks specific service
                            return False, f"entity {eid} service {service} blocked by role {user_role}"
        else:
            # Same logic for single entity
            default_entities = default_restrictions.get("entities", {})
            if entity_id in default_entities:
                default_entity_config = default_entities[entity_id]
                default_entity_services = default_entity_config.get("services", [])
                default_entity_allow = default_entity_config.get("allow", False)
                
                if default_entity_allow:
                    # Default allow rule: check if service is in allowed services
                    if not default_entity_services or service in default_entity_services:
                        return True, f"entity {entity_id} service {service} allowed by default"
                    else:
                        return False, f"entity {entity_id} service {service} not in default allow list"
                else:
                    # Default block rule
                    if not default_entity_services:  # Default blocks all services
                        role_entities = permissions.get("entities", {})
                        if entity_id not in role_entities:
                            return False, f"entity {entity_id} blocked by default restrictions"
                        role_entity_config = role_entities[entity_id]
                        role_entity_services = role_entity_config.get("services", [])
                        role_entity_allow = role_entity_config.get("allow", False)
                        
                        if role_entity_allow:
                            # Role allow rule: check if service is in allowed services
                            if not role_entity_services or service in role_entity_services:
                                return True, f"entity {entity_id} service {service} allowed by role {user_role}"
                            else:
                                return False, f"entity {entity_id} service {service} not in role allow list"
                        else:
                            # Role block rule
                            if not role_entity_services:  # Role also blocks all services
                                return False, f"entity {entity_id} blocked by role {user_role}"
                            elif service not in role_entity_services:  # Service not in role's allowed list
                                return False, f"entity {entity_id} service {service} not allowed by role {user_role}"
                    elif service in default_entity_services:  # Default blocks specific service
                        role_entities = permissions.get("entities", {})
                        if entity_id not in role_entities:
                            return False, f"entity {entity_id} service {service} blocked by default restrictions"
                        role_entity_config = role_entities[entity_id]
                        role_entity_services = role_entity_config.get("services", [])
                        role_entity_allow = role_entity_config.get("allow", False)
                        
                        if role_entity_allow:
                            # Role allow rule: check if service is in allowed services
                            if not role_entity_services or service in role_entity_services:
                                return True, f"entity {entity_id} service {service} allowed by role {user_role}"
                            else:
                                return False, f"entity {entity_id} service {service} not in role allow list"
                        else:
                            # Role block rule
                            if service in role_entity_services:  # Role also blocks this service
                                return False, f"entity {entity_id} service {service} blocked by role {user_role}"
            
            # Check role-specific entity restrictions (always check, even if no default restrictions)
            role_entities = permissions.get("entities", {})
            if entity_id in role_entities:
                role_entity_config = role_entities[entity_id]
                role_entity_services = role_entity_config.get("services", [])
                role_entity_allow = role_entity_config.get("allow", False)
                
                _LOGGER.warning(f"Found single entity {entity_id} in role permissions: allow={role_entity_allow}, services={role_entity_services}")
                
                if role_entity_allow:
                    # Role allow rule: check if service is in allowed services
                    if not role_entity_services or service in role_entity_services:
                        return True, f"entity {entity_id} service {service} allowed by role {user_role}"
                    else:
                        return False, f"entity {entity_id} service {service} not in role allow list"
                else:
                    # Role block rule
                    if not role_entity_services:  # Role blocks all services for this entity
                        return False, f"entity {entity_id} blocked by role {user_role}"
                    elif service in role_entity_services:  # Role blocks specific service
                        return False, f"entity {entity_id} service {service} blocked by role {user_role}"

    # Area (room) rules: more specific than domain rules, less specific than entity rules
    if hass and permissions.get("areas"):
        area_result = _check_area_access(
            hass, domain, service, service_data, target, permissions, default_restrictions, user_role
        )
        if area_result is not None:
            return area_result

    default_domains = default_restrictions.get("domains", {})
    role_domains = permissions.get("domains", {})
    
    if domain in default_domains:
        default_config = default_domains[domain]
        default_services = default_config.get("services", [])
        default_allow = default_config.get("allow", False)
        
        if default_allow:
            if not default_services or service in default_services:
                return True, f"domain {domain} service {service} allowed by default"
            else:
                return False, f"domain {domain} service {service} not in default allow list"
        else:
            if not default_services:
                if domain not in role_domains:
                    return False, f"domain {domain} blocked by default restrictions"
                role_config = role_domains[domain]
                role_services = role_config.get("services", [])
                role_allow = role_config.get("allow", False)
                
                if role_allow:
                    if not role_services or service in role_services:
                        return True, f"domain {domain} service {service} allowed by role {user_role}"
                    else:
                        return False, f"domain {domain} service {service} not in role allow list"
                else:
                    if not role_services:
                        return False, f"domain {domain} blocked by role {user_role}"
                    elif service not in role_services:
                        return False, f"service {domain}.{service} not allowed by role {user_role}"
            elif service in default_services:
                if domain not in role_domains:
                    return False, f"service {domain}.{service} blocked by default restrictions"
                role_config = role_domains[domain]
                role_services = role_config.get("services", [])
                role_allow = role_config.get("allow", False)
                
                if role_allow:
                    if not role_services or service in role_services:
                        return True, f"domain {domain} service {service} allowed by role {user_role}"
                    else:
                        return False, f"domain {domain} service {service} not in role allow list"
                else:
                    if service in role_services:
                        return False, f"service {domain}.{service} blocked by role {user_role}"
    
    if domain in role_domains:
        role_config = role_domains[domain]
        role_services = role_config.get("services", [])
        role_allow = role_config.get("allow", False)
        
        _LOGGER.warning(f"Found domain {domain} in role permissions: allow={role_allow}, services={role_services}")
        
        if role_allow:
            if not role_services or service in role_services:
                return True, f"domain {domain} service {service} allowed by role {user_role}"
            else:
                return False, f"domain {domain} service {service} not in role allow list"
        else:
            if not role_services:
                return False, f"domain {domain} blocked by role {user_role}"
            elif service in role_services:
                return False, f"service {domain}.{service} blocked by role {user_role}"
    
    if deny_all and not ((domain == "system_log" and service == "write") or (domain == "browser_mod" and service == "notification")):
        entity_ids = []
        
        if service_data and "entity_id" in service_data:
            entity_id = service_data["entity_id"]
            if isinstance(entity_id, str):
                entity_ids = [entity_id]
            else:
                entity_ids = entity_id if isinstance(entity_id, list) else []
        
        if domain in ["script", "automation"]:
            entity_name = f"{domain}.{service}"
            entity_ids.append(entity_name)
        
        role_entities = permissions.get("entities", {})
        for eid in entity_ids:
            if eid in role_entities:
                entity_config = role_entities[eid]
                entity_allow = entity_config.get("allow", False)
                if entity_allow:
                    entity_services = entity_config.get("services", [])
                    if not entity_services or service in entity_services:
                        return True, f"entity {eid} service {service} allowed by role entity permissions (overrides deny_all)"
        
        return False, f"access denied by deny_all setting for role {user_role}"
    
    return True, f"access granted"


def _check_service_access(
    domain: str,
    service: str,
    service_data: Optional[Dict[str, Any]],
    user_id: Optional[str],
    access_config: Dict[str, Any],
    hass: HomeAssistant = None,
    target: Optional[Dict[str, Any]] = None
) -> bool:
    """Check if a user has access to a specific service call."""
    result, _ = _check_service_access_with_reason(domain, service, service_data, user_id, access_config, hass, target)
    return result


def _check_entity_access_with_reason(entity_id: str, service: str, user_config: Dict[str, Any]) -> tuple[bool, str]:
    """Check if user has access to a specific entity service with detailed reason."""
    if not user_config:
        return True, f"no user config"
    
    restrictions = user_config.get("restrictions", {})
    entities = restrictions.get("entities", {})
    
    if entity_id in entities:
        entity_config = entities[entity_id]
        
        if entity_config.get("allow", False):
            services = entity_config.get("services", [])
            if not services or service in services:
                return True, f"entity {entity_id} service {service} allowed"
            else:
                return False, f"entity {entity_id} service {service} not in allow list"
        
        if entity_config.get("hide", False):
            return False, f"entity {entity_id} blocked"
        services = entity_config.get("services", [])
        if service in services:
            return False, f"entity {entity_id} service {service} blocked"
    
    return True, f"entity {entity_id} allowed"


def _check_domain_access_with_reason(domain: str, service: str, user_config: Dict[str, Any]) -> tuple[bool, str]:
    """Check if user has access to a domain service with detailed reason."""
    if not user_config:
        return True, f"no user config"
    
    restrictions = user_config.get("restrictions", {})
    domains = restrictions.get("domains", {})
    
    if domain in domains:
        domain_config = domains[domain]
        
        if domain_config.get("allow", False):
            services = domain_config.get("services", [])
            if not services or service in services:
                return True, f"domain {domain} service {service} allowed"
            else:
                return False, f"domain {domain} service {service} not in allow list"
        
        # Block rule: if domain is hidden, hide all services
        if domain_config.get("hide", False):
            return False, f"domain {domain} blocked"
        # Check specific service restrictions
        services = domain_config.get("services", [])
        if service in services:
            return False, f"domain {domain} service {service} blocked"
    
    return True, f"domain {domain} allowed"


def _check_restriction_access_with_reason(
    domain: str,
    service: str,
    service_data: Optional[Dict[str, Any]],
    user_config: Dict[str, Any]
) -> tuple[bool, str]:
    """Check if service is in user's restrictions with detailed reason."""
    if not user_config:
        return False, f"no user config"
    
    restrictions = user_config.get("restrictions", {})
    domains = restrictions.get("domains", {})
    
    if domain in domains:
        domain_config = domains[domain]
        services = domain_config.get("services", [])
        if service in services:
            return True, f"service {domain}.{service} restricted"
    
    return False, f"service {domain}.{service} allowed"


def get_user_config(hass: HomeAssistant, user_id: str) -> Optional[Dict[str, Any]]:
    """Get the configuration for a specific user."""
    if DOMAIN not in hass.data:
        return None
    
    access_config = hass.data[DOMAIN].get("access_config", {})
    users = access_config.get("users", {})
    return users.get(user_id)


async def reload_access_config(hass: HomeAssistant) -> bool:
    """Reload the access control configuration from YAML file."""
    try:
        access_config = await _load_access_control_config(hass)
        hass.data[DOMAIN]["access_config"] = access_config
        _LOGGER.info("Access control configuration reloaded successfully")
        return True
    except Exception as e:
        _LOGGER.error(f"Failed to reload access control configuration: {e}")
        return False


def _is_top_level_user(hass: HomeAssistant, user_id: str) -> bool:
    """Check if user has top-level access (admin or super_admin role)."""
    if DOMAIN not in hass.data:
        return False
    
    access_config = hass.data[DOMAIN].get("access_config", {})
    users = access_config.get("users", {})
    user_config = users.get(user_id)
    
    if not user_config:
        try:
            user = hass.auth.async_get_user(user_id)
            if user and user.is_admin:
                return True
        except Exception:
            pass
        return False
    
    role = user_config.get("role", "")
    return role in ["admin", "super_admin"]


async def _save_access_control_config(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Save access control configuration to YAML file."""
    config_path = _storage_path(hass, ACCESS_CONTROL_FILE)
    
    def _save_file():
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, indent=2, sort_keys=False)
            return True
        except Exception as e:
            _LOGGER.error(f"Error saving access control configuration: {e}")
            return False
    
    success = await hass.async_add_executor_job(_save_file)
    if success:
        _LOGGER.info(f"Saved access control configuration to {config_path}")
    return success


def _log_denial_to_file(hass: HomeAssistant, user_id: str, user_name: str, user_role: str, domain: str, service: str, reason: str):
    """Log access denial to deny_list.log file."""
    try:
        log_path = _storage_path(hass, DENY_LOG_FILE)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = f"[{timestamp}] DENIED - User: {user_name} ({user_id}) | Role: {user_role} | Service: {domain}.{service} | Reason: {reason}\n"
        
        with open(log_path, 'a', encoding='utf-8') as log_file:
            log_file.write(log_entry)
        
        _LOGGER.debug(f"Logged denial to deny_list.log: {user_name} -> {domain}.{service}")
        
    except Exception as e:
        _LOGGER.error(f"Failed to log denial to file: {e}")


def _get_deny_log_contents(hass: HomeAssistant) -> str:
    """Get the contents of the deny_list.log file."""
    try:
        log_path = _storage_path(hass, DENY_LOG_FILE)
        
        if not os.path.exists(log_path):
            return "No deny log file found. Denials will be logged here when they occur."
        
        with open(log_path, 'r', encoding='utf-8') as log_file:
            contents = log_file.read()
        
        if not contents.strip():
            return "Deny log file is empty. No access denials have been logged yet."
        
        return contents
        
    except Exception as e:
        _LOGGER.error(f"Failed to read deny log file: {e}")
        return f"Error reading deny log file: {e}"


def _clear_deny_log(hass: HomeAssistant) -> bool:
    """Clear the contents of the deny_list.log file."""
    try:
        log_path = _storage_path(hass, DENY_LOG_FILE)
        
        with open(log_path, 'w', encoding='utf-8') as log_file:
            log_file.write("")
        
        _LOGGER.info("Deny log file cleared successfully")
        return True
        
    except Exception as e:
        _LOGGER.error(f"Failed to clear deny log file: {e}")
        return False


async def _register_sidebar_panel(hass: HomeAssistant):
    """Register RBAC configuration panel in the sidebar."""
    
    should_show_panel = True
    
    for entry in hass.config_entries.async_entries(DOMAIN):
        should_show_panel = entry.options.get("show_sidebar_panel", True)
        break
    
    if not should_show_panel:
        _LOGGER.info("RBAC sidebar panel disabled via config entry options")
        return
    
    async def _do_panel_registration():
        """Perform the actual panel registration."""
        try:
            from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel
            
            try:
                await async_remove_panel(hass, "rbac-config")
            except Exception:
                pass
            
            async_register_built_in_panel(
                hass,
                component_name="iframe",
                sidebar_title="RBAC Config",
                sidebar_icon="mdi:shield-account",
                frontend_url_path="rbac-config",
                config={
                    "url": "/api/rbac/static/config.html",
                    "title": "RBAC Configuration"
                },
                require_admin=True
            )
            _LOGGER.info("Successfully registered RBAC sidebar panel")
            return True
            
        except Exception as e:
            _LOGGER.debug(f"Panel registration attempt failed: {e}")
            return False
    
    if await _do_panel_registration():
        return
    
    async def _on_frontend_ready(event):
        """Handle frontend ready event."""
        if await _do_panel_registration():
            return
        
        import asyncio
        await asyncio.sleep(2)
        
        if not await _do_panel_registration():
            _LOGGER.warning("Could not register RBAC sidebar panel. Users will need to access the config page manually at /api/rbac/static/config.html")
    
    try:
        hass.bus.async_listen_once("frontend_ready", _on_frontend_ready)
        _LOGGER.info("RBAC panel registration scheduled for when frontend is ready")
    except Exception as e:
        _LOGGER.warning(f"Could not schedule RBAC panel registration: {e}. Users will need to access the config page manually at /api/rbac/static/config.html")


async def add_user_access(hass: HomeAssistant, user_id: str, role: str) -> bool:
    """Add a user to the access control configuration."""
    if DOMAIN not in hass.data:
        return False
    
    access_config = hass.data[DOMAIN].get("access_config", {})
    if "users" not in access_config:
        access_config["users"] = {}
    
    access_config["users"][user_id] = {
        "role": role
    }
    
    if await _save_access_control_config(hass, access_config):
        hass.data[DOMAIN]["access_config"] = access_config
        _LOGGER.info(f"Added user '{user_id}' with role '{role}'")
        return True
    
    return False


async def remove_user_access(hass: HomeAssistant, user_id: str) -> bool:
    """Remove a user from the access control configuration."""
    if DOMAIN not in hass.data:
        return False
    
    access_config = hass.data[DOMAIN].get("access_config", {})
    users = access_config.get("users", {})
    
    if user_id in users:
        del users[user_id]
        
        if _save_access_control_config(hass, access_config):
            hass.data[DOMAIN]["access_config"] = access_config
            _LOGGER.info(f"Removed user '{user_id}' from access control")
            return True
    
    return False


async def update_user_role(hass: HomeAssistant, user_id: str, role: str) -> bool:
    """Update a user's role in the access control configuration."""
    if DOMAIN not in hass.data:
        return False
    
    access_config = hass.data[DOMAIN].get("access_config", {})
    users = access_config.get("users", {})
    
    if user_id in users:
        users[user_id]["role"] = role
        
        if _save_access_control_config(hass, access_config):
            hass.data[DOMAIN]["access_config"] = access_config
            _LOGGER.info(f"Updated user '{user_id}' role to '{role}'")
            return True
    
    return False


async def add_user_restriction(hass: HomeAssistant, user_id: str, domain: str, services: list) -> bool:
    """Add domain restrictions for a user."""
    if DOMAIN not in hass.data:
        return False
    
    access_config = hass.data[DOMAIN].get("access_config", {})
    users = access_config.get("users", {})
    
    if user_id not in users:
        return False
    
    user_config = users[user_id]
    if "restrictions" not in user_config:
        user_config["restrictions"] = {}
    if "domains" not in user_config["restrictions"]:
        user_config["restrictions"]["domains"] = {}
    
    user_config["restrictions"]["domains"][domain] = {
        "services": services
    }
    
    if await _save_access_control_config(hass, access_config):
        hass.data[DOMAIN]["access_config"] = access_config
        _LOGGER.info(f"Added domain restriction for user '{user_id}': {domain}.{services}")
        return True
    
    return False


async def remove_user_restriction(hass: HomeAssistant, user_id: str, domain: str) -> bool:
    """Remove domain restrictions for a user."""
    if DOMAIN not in hass.data:
        return False
    
    access_config = hass.data[DOMAIN].get("access_config", {})
    users = access_config.get("users", {})
    
    if user_id not in users:
        return False
    
    user_config = users[user_id]
    restrictions = user_config.get("restrictions", {})
    domains = restrictions.get("domains", {})
    
    if domain in domains:
        del domains[domain]
        
        if await _save_access_control_config(hass, access_config):
            hass.data[DOMAIN]["access_config"] = access_config
            _LOGGER.info(f"Removed domain restriction for user '{user_id}': {domain}")
            return True
    
    return False


