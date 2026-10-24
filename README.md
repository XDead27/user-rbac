<p align="center">
  <img src="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/logo.png" alt="Home Assistant RBAC Logo" width="180" />
</p>

<h1 align="center">🏠 Home Assistant RBAC Middleware</h1>

<p align="center">
  Finally, a flexible Role-Based Access Control (RBAC) middleware component for Home Assistant that intercepts service calls and enforces access control based on YAML configuration.<br>
  Configure roles and user permissions using the fancy GUI editor, or configure in the YAML file directly.
</p>

## 📸 Gallery

<div align="center">
  <table>
    <tr>
      <td align="center">
        <a href="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/editing-role.png" target="_blank">
          <img src="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/editing-role.png" alt="Role Editing" width="350"/>
        </a>
        <br><strong>Role Editing</strong>
        <br><em>Detailed role configuration and permission settings</em>
      </td>
      <td align="center">
        <a href="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/editing-guest-role.png" target="_blank">
          <img src="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/editing-guest-role.png" alt="Guest Role Configuration" width="350"/>
        </a>
        <br><strong>Guest Role Configuration</strong>
        <br><em>Guest user role with template condition</em>
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/role-management.png" target="_blank">
          <img src="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/role-management.png" alt="Role Management" width="350"/>
        </a>
        <br><strong>Role Management</strong>
        <br><em>Overview of all configured roles and their settings</em>
      </td>
      <td align="center">
        <a href="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/user-role-assignment.png" target="_blank">
          <img src="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/user-role-assignment.png" alt="User Role Assignment" width="350"/>
        </a>
        <br><strong>User Role Assignment</strong>
        <br><em>Assigning roles to Home Assistant users</em>
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/settings-and-default-restrictions.png" target="_blank">
          <img src="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/settings-and-default-restrictions.png" alt="Settings and Default Restrictions" width="350"/>
        </a>
        <br><strong>Settings and Default Restrictions</strong>
        <br><em>System-wide settings and default access controls</em>
      </td>
      <td align="center">
        <a href="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/deny-log.png" target="_blank">
          <img src="https://raw.githubusercontent.com/SamAthanas/user-rbac/main/screenshots/deny-log.png" alt="Deny Log" width="350"/>
        </a>
        <br><strong>Deny Log</strong>
        <br><em>Track and monitor denied access attempts</em>
      </td>
    </tr>
  </table>
</div>

## ⚠️ Notice:
This application is under active development and is not stable yet!
Its ideal for users who want to experiment with basic role based access, and restrict others from being able to call specific actions on your home server. (Perhaps this will finally put an end to people expoiting the search feature or widgets to call actions that are not on your dashboard!) This component has been tested on my own instance quite a bit, but there will likely be some bugs that remain. Feel free to contribute directly or raise an issue if there is something you would like tweaked.

Due to the nature of this application patching core functions, its possible that it will break in future updates of home assistant. If this occurs, you may disable the component until its updated to work with the latest version. Disabling the component will cause home assistant to return back to its normal state, without any of the rbac blocking features.

## ✨ Features
- **Service Call Interception**: Automatically intercepts all Home Assistant service calls.
- **YAML-Based Configuration**: Ability to define access control rules in a YAML file.
- **Modernized Frontend for Configuration**: Alternatively use the admin frontend to configure the access control rules.
- **Domain and Entity Level Control**: Restrict access at both domain and entity levels.
- **Room (Area) Level Control**: Allow or block everything assigned to a Home Assistant area (devices, scenes, scripts, etc.), e.g. a role that can only control the kitchen.
- **Action/Service call Control**: Restrict actions on specific domains or entities, or restrict all actions tied to an entity.
- **Allow All and Deny All settings supported**: Configure roles to allow everything, with specific blocked entities or block everything, with specific allowed entities.
- **Frontend Blocking**: Remove blocked entities from the native HA quickbar
- **Dynamic Configuration**: Reload configuration without restarting Home Assistant
- **Notifications+Events**: Persistant notifications and events are sent when system denies action call.
- **Service Management**: Built-in services to manage and inspect configuration.
- **Deploy Scripts for Development**: vs-code scripts included to auto ssh into server to copy files based on .env variables, and auto restarts HA after deployment for streamlined dev workflow.

## 🚀 Installation

### HACS Store
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SamAthanas&category=Integration&repository=user-rbac)

> After installation, restart home assistant and add the RBAC Middleware Service. Configure the settings in the side panel.
---
### (Manual Method)
- Copy the files to your server first
  - Component: custom_components/rbac
  - Frontend Script (Add to resources, Javascript Module): /api/rbac/static/rbac.js
- OR utilize the deploy.sh script to deploy to your instance directly. this requires setting up a .env file in the root of this project to configure your ssh settings
- Search for the 'RBAC' (Role Based Access Control) Integration and install it
- Ensure you are logged in as an admin user, and then access this page <YOUR_HA_DOMAIN>/api/rbac/static/config.html
- Configure Roles and Role Assignments
- Changes to the config take effect immediantly without any restart needed
- Test with users to ensure denied action calls are blocked

## 🚪 Room-Based Access (Areas)
Roles can contain area rules next to domain and entity rules. An entity belongs to an area if the entity itself is assigned to it, or otherwise if its device is. Scenes, scripts and automations only count when you assign them an area.

A role that can only control the kitchen:
```yaml
roles:
  kitchen_only:
    description: Can only control the kitchen
    deny_all: true
    permissions:
      areas:
        kitchen:          # area_id
          allow: true
          services: []    # empty = all services
```
- Precedence: entity rules > area rules > domain rules > Allow All / Deny All.
- Calls targeting `area_id`, `device_id`, `floor_id` or `label_id` are expanded to their entities for area rules; a call is only allowed by an area rule when **every** targeted entity is allowed.
- Area rules use the same allow/block + optional services format as domain and entity rules, so you can also block a single room in an Allow All role.

## 💡 Creative Ideas
- Restrict non household users to sensitive domains like 'light', 'camera', or home assistant shutdown services
- Create a guest role that utilizes the current user context in a template to determine if they should have access to your homes entities based on if they are within proximity of your house ('Guest' role is used when they are not at 'home', 'User' role is used if they are at home) {{ states[current_user_str].state != 'home'}}

## 📝 Notes
- Admin users or users assigned an admin role will be able to access the RBAC configuration page 
- Its possible to assign templates to each role. Templates will be evaluated each time a user that has that role executes a service call. The template will determine if the users role should be used, or if it should fallback to a different role with an entierly different set of permissions. This makes it possible to create more complex auth systems based on current states from your HA instance.
- Default domain/enttiy blocklists are supported. Any non-admin user will always have these restrictions enforced.
- Frontend is built using Preact that compiles into a static page, for easier state management and component isolation.

## 💡 Future Ideas
> **Note:** The following are some future ideas for this project. Not all of these may be possible to implement.
- Add an option to create a temporary guest page to grant temporary access to specific entities without needing to create a guest account
  - Add a date range or template to determine if the guest page should be active
- Lock down the entity list so that the backend can only return the entities that a user has access to, without needing to rely on a frontend filtering script
- Add a backend option to restrict users from being able to see the current values of entities
- Add the ability to restrict camera feeds from displaying to users without access
- Send notifications to users that were blocked from accessing a service
- Intercept voice commands to return an error message if the user tried to access a blocked service. Right now the returned response always indicates success even if the service call was blocked.


## 🤝 Contributing
Contributions are welcome and much appreciated!
There are vscode scripts included to easily deploy changes made to the backend or frontend, and auto retart HA when complete.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

Alternatively, you may submit an issue if you encounter a problem or want to request a new feature.

<p>
  <a href="https://buymeacoffee.com/samathanas" target="_blank">
    <img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-☕-yellow.svg" alt="Buy me a coffee" />
  </a>
  <br>
  <small><em>If you like my work, consider supporting me using the buy me a coffee link!</em></small>
</p>

## 📄 License
This project is licensed under the MIT License.
