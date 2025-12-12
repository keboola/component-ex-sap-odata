#!/usr/bin/env python3
"""
Keboola Component Schema Tester
================================

A unified Flask-based testing server for Keboola component schemas.

Features:
- Auto-discovers component_config/ folder and schemas
- Loads existing config.json and pre-fills forms
- Serves embedded HTML schema tester UI
- Handles all sync actions with automatic component integration
- Zero configuration required - just run it!

Usage:
    python component_schema_tester.py

    Then open: http://localhost:8000
"""

import os
import sys
import json
from pathlib import Path
from flask import Flask, jsonify, request, Response
from flask_cors import CORS

# ============================================================================
# AUTO-DISCOVERY FUNCTIONS
# ============================================================================

def find_project_root():
    """
    Find project root by looking for component_config/ folder.

    Searches upward from the script location until it finds a directory
    containing a component_config/ folder.

    Returns:
        str: Path to project root, or None if not found
    """
    current = os.path.dirname(os.path.abspath(__file__))
    max_depth = 10  # Prevent infinite loops
    depth = 0

    while current != '/' and depth < max_depth:
        if os.path.exists(os.path.join(current, 'component_config')):
            return current
        current = os.path.dirname(current)
        depth += 1

    return None


def find_component_config(project_root):
    """
    Return path to component_config folder.

    Args:
        project_root (str): Path to project root

    Returns:
        str: Path to component_config directory
    """
    return os.path.join(project_root, 'component_config')


def find_config_json(project_root):
    """
    Return path to data/config.json if exists, else None.

    Args:
        project_root (str): Path to project root

    Returns:
        str: Path to config.json if it exists, None otherwise
    """
    path = os.path.join(project_root, 'data', 'config.json')
    return path if os.path.exists(path) else None


def write_config(project_root, parameters):
    """
    Write configuration to data/config.json for component sync actions.

    Args:
        project_root (str): Path to project root
        parameters (dict): Configuration parameters to write
    """
    data_dir = os.path.join(project_root, 'data')
    os.makedirs(data_dir, exist_ok=True)

    config_path = os.path.join(data_dir, 'config.json')
    config = {
        'parameters': parameters
    }

    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)


# ============================================================================
# FLASK APP SETUP
# ============================================================================

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global variables set during initialization
project_root = None
component_config_path = None
config_json_path = None


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/')
def index():
    """Serve the embedded HTML schema tester."""
    return Response(HTML_CONTENT, mimetype='text/html')


@app.route('/api/discovery-info', methods=['GET'])
def get_discovery_info():
    """
    Return auto-discovered paths for manual input pre-fill.

    Returns:
        JSON response with componentConfig and configJson paths
    """
    return jsonify({
        'componentConfig': component_config_path if component_config_path else None,
        'configJson': config_json_path if config_json_path else None
    })


@app.route('/api/schemas', methods=['GET'])
def get_schemas():
    """
    Return both component and row schemas.

    Query Parameters:
        path: Optional manual path to component_config folder

    Returns:
        JSON response with componentSchema and rowSchema objects
    """
    try:
        # Use manual path if provided, otherwise use auto-discovered path
        manual_path = request.args.get('path')
        config_path = manual_path if manual_path else component_config_path

        if not config_path or not os.path.exists(config_path):
            return jsonify({'error': f'Component config folder not found: {config_path}'}), 404

        config_schema_path = os.path.join(config_path, 'configSchema.json')
        row_schema_path = os.path.join(config_path, 'configRowSchema.json')

        with open(config_schema_path) as f:
            component_schema = json.load(f)

        with open(row_schema_path) as f:
            row_schema = json.load(f)

        return jsonify({
            'componentSchema': component_schema,
            'rowSchema': row_schema
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['GET'])
def get_config():
    """
    Return config.json parameters if exists.

    Query Parameters:
        path: Optional manual path to config.json file

    Returns:
        JSON response with parameters object (empty if no config)
    """
    # Use manual path if provided, otherwise use auto-discovered path
    manual_path = request.args.get('path')
    config_path = manual_path if manual_path else config_json_path

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
                return jsonify(config.get('parameters', {}))
        except Exception as e:
            print(f"Warning: Could not read config.json: {e}")
            return jsonify({})

    return jsonify({})


@app.route('/sync-action', methods=['POST'])
def sync_action():
    """
    Handle ALL sync actions by calling the Component class.

    Request JSON:
        {
            "action": "actionName",
            "parameters": {...}
        }

    Returns:
        JSON response from the sync action
    """
    try:
        data = request.json
        action = data.get('action')
        parameters = data.get('parameters', {})

        # Write config for Component to read
        write_config(project_root, parameters)

        # Import and create component instance
        try:
            from component import Component
        except ImportError:
            return jsonify({
                'status': 'error',
                'message': 'Could not import Component from src/component.py'
            }), 500

        comp = Component()

        # Map action names to component methods
        action_map = {
            'testConnection': comp.test_connection,
            'loadEntities': comp.load_entities,
            'loadFields': comp.load_fields,
            'loadPossiblePrimaryKeys': comp.load_possible_primary_keys,
            'loadIncrementalFields': comp.load_incremental_fields,
            'loadNavigationProperties': comp.load_navigation_properties,
            'previewData': comp.preview_data,
            'validateFilter': comp.validate_filter,
        }

        if action not in action_map:
            return jsonify({
                'status': 'error',
                'message': f'Unknown action: {action}'
            }), 400

        # Call the action and return result
        result = action_map[action]()
        return jsonify(result)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in sync action: {error_trace}")

        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': error_trace
        }), 500


# ============================================================================
# EMBEDDED HTML CONTENT
# ============================================================================

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Keboola Component Schema Tester</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@json-editor/json-editor@latest/dist/css/jsoneditor.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css">
    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@json-editor/json-editor@latest/dist/jsoneditor.min.js"></script>
    <style>
        body {
            padding: 20px;
            background: linear-gradient(135deg, #1BC98E 0%, #0097A7 100%);
            min-height: 100vh;
        }
        .main-container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #1BC98E 0%, #0097A7 100%);
            color: white;
            padding: 30px;
            text-align: center;
            position: relative;
        }
        .logo {
            font-size: 3rem;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
        }
        .logo-icon {
            font-size: 2.5rem;
        }
        .logo-text {
            font-size: 1.8rem;
            font-weight: 700;
            letter-spacing: 1px;
        }
        .header h1 {
            margin: 10px 0 0 0;
            font-size: 1.5rem;
            font-weight: 600;
        }
        .header .credits {
            margin-top: 15px;
            font-size: 0.9rem;
            opacity: 0.9;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .sidebar .reload-button {
            width: 100%;
            background: #1BC98E;
            border: none;
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
            margin-bottom: 25px;
            font-size: 1rem;
        }
        .sidebar .reload-button:hover {
            background: #0097A7;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(27, 201, 142, 0.3);
        }
        .content {
            display: flex;
            gap: 0;
            min-height: calc(100vh - 200px);
        }
        .sidebar {
            width: 320px;
            background: #f8f9fa;
            padding: 25px;
            border-right: 2px solid #dee2e6;
            overflow-y: auto;
        }
        .sidebar h3 {
            font-size: 1rem;
            font-weight: 700;
            color: #495057;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .main-content {
            flex: 1;
            padding: 30px;
            overflow-y: auto;
        }
        .nav-tabs {
            border-bottom: 2px solid #dee2e6;
            margin-bottom: 30px;
        }
        .nav-tabs .nav-link {
            border: none;
            color: #6c757d;
            font-weight: 600;
            padding: 15px 30px;
            transition: all 0.3s;
        }
        .nav-tabs .nav-link:hover {
            color: #1BC98E;
            background: #f8f9fa;
        }
        .nav-tabs .nav-link.active {
            color: #1BC98E;
            border-bottom: 3px solid #1BC98E;
            background: transparent;
        }
        .tab-content {
            min-height: 400px;
        }
        .schema-section {
            margin-bottom: 40px;
            padding: 25px;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            background-color: #f8f9fa;
        }
        .schema-section h2 {
            font-size: 1.5rem;
            margin-bottom: 20px;
            color: #0097A7;
            padding-bottom: 10px;
            border-bottom: 2px solid #dee2e6;
        }
        .form-container {
            background: white;
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .output-section {
            margin-top: 20px;
            padding: 15px;
            background-color: #e9ecef;
            border-radius: 4px;
            border-left: 4px solid #1BC98E;
        }
        .output-section h3 {
            font-size: 1rem;
            margin-bottom: 10px;
            color: #1BC98E;
        }
        .output-section pre {
            background-color: #fff;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            max-height: 400px;
        }
        .je-object__container {
            padding: 15px;
            background: white;
            border-radius: 4px;
        }
        .btn-primary {
            background: #1BC98E;
            border: none;
            padding: 12px 30px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 10px;
        }
        .btn-primary:hover {
            background: #15B67D;
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(27, 201, 142, 0.3);
        }
        .btn-success {
            background: #0097A7;
            border: none;
            padding: 12px 30px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-success:hover {
            background: #00838F;
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0, 151, 167, 0.3);
        }
        .badge {
            font-size: 0.75rem;
            padding: 4px 8px;
            margin-left: 8px;
            vertical-align: middle;
        }
        .combined-config {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 8px;
        }
        .combined-config h3 {
            color: #0097A7;
            margin-bottom: 15px;
        }
        .combined-config .help-text {
            color: #6c757d;
            margin-bottom: 20px;
            padding: 15px;
            background: white;
            border-left: 4px solid #1BC98E;
            border-radius: 4px;
        }
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .alert-info {
            background: white;
            border: 1px solid #dee2e6;
            color: #495057;
        }
        .alert-info strong {
            color: #1BC98E;
            display: block;
            margin-bottom: 10px;
        }
        .alert-info ul {
            margin: 0;
            padding-left: 20px;
            font-size: 0.9rem;
            line-height: 1.8;
        }
        .alert-success {
            background: #d4edda;
            border: 1px solid #1BC98E;
            color: #155724;
            font-size: 0.9rem;
        }
        .alert-danger {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            font-size: 0.9rem;
        }
        .status-box {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #dee2e6;
        }
        .status-box h4 {
            font-size: 0.9rem;
            font-weight: 700;
            color: #495057;
            margin-bottom: 10px;
        }
        .status-box .path-item {
            font-size: 0.85rem;
            margin-bottom: 8px;
            padding: 8px;
            background: #f8f9fa;
            border-radius: 4px;
            font-family: monospace;
            word-break: break-all;
        }
        .status-box .path-label {
            color: #1BC98E;
            font-weight: 600;
            margin-right: 8px;
        }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="header">
            <div class="logo">
                <span class="logo-icon">🏭</span>
                <span class="logo-text">COMPONENT FACTORY</span>
            </div>
            <h1>Schema Tester</h1>
            <div class="credits">
                <span>by Component Factory Team</span>
                <span style="opacity: 0.7;">•</span>
                <span style="opacity: 0.7;">Keboola Platform</span>
            </div>
        </div>

        <div class="content">
            <!-- Sidebar -->
            <div class="sidebar">
                <button class="reload-button" onclick="reloadSchemas()">🔄 Reload Schemas</button>

                <h3>Paths</h3>
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 0.85rem; margin-bottom: 5px; color: #495057;">
                        Component Config:
                    </label>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <input
                            type="text"
                            id="manual-component-config"
                            placeholder="Auto-discovered..."
                            readonly
                            style="flex: 1; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px; font-size: 0.85rem; background: #f8f9fa;"
                        />
                        <button
                            onclick="document.getElementById('folder-picker').click()"
                            style="padding: 8px 12px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;"
                            title="Select folder"
                        >
                            📁
                        </button>
                    </div>
                    <input type="file" id="folder-picker" webkitdirectory directory style="display: none;" onchange="handleFolderSelect(event)" />

                    <label style="display: block; font-size: 0.85rem; margin-top: 12px; margin-bottom: 5px; color: #495057;">
                        Config JSON:
                    </label>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <input
                            type="text"
                            id="manual-config-json"
                            placeholder="Auto-discovered..."
                            readonly
                            style="flex: 1; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px; font-size: 0.85rem; background: #f8f9fa;"
                        />
                        <button
                            onclick="document.getElementById('file-picker').click()"
                            style="padding: 8px 12px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;"
                            title="Select file"
                        >
                            📄
                        </button>
                    </div>
                    <input type="file" id="file-picker" accept=".json" style="display: none;" onchange="handleFileSelect(event)" />
                </div>

                <div id="status" style="margin-bottom: 15px;"></div>

                <h3>Quick Start</h3>
                <div class="alert alert-info">
                    <strong>💡 Usage:</strong>
                    <ul>
                        <li>Paths are auto-discovered on load</li>
                        <li>Use 📁/📄 buttons to change paths manually</li>
                        <li>Click "🔄 Reload Schemas" to apply changes</li>
                    </ul>
                </div>
            </div>

            <!-- Main Content -->
            <div class="main-content">

                <!-- Tabs Navigation -->
                <ul class="nav nav-tabs" id="configTabs" role="tablist">
                    <li class="nav-item" role="presentation">
                        <button class="nav-link active" id="component-tab" data-bs-toggle="tab" data-bs-target="#component-pane" type="button" role="tab">
                            📋 Schema configuration
                        </button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" id="row-tab" data-bs-toggle="tab" data-bs-target="#row-pane" type="button" role="tab">
                            🔧 Row schema configuration
                        </button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" id="combined-tab" data-bs-toggle="tab" data-bs-target="#combined-pane" type="button" role="tab">
                            📦 Resulting configuration
                        </button>
                    </li>
                </ul>

            <!-- Tab Content -->
            <div class="tab-content" id="configTabContent">
                <!-- Component Configuration Tab -->
                <div class="tab-pane fade show active" id="component-pane" role="tabpanel">
                    <div class="schema-section">
                        <h2>Component Configuration</h2>
                        <small class="text-muted">Global settings shared across all configuration rows</small>
                        <div class="form-container">
                            <div id="component-editor"></div>
                            <button class="btn-primary" onclick="validateComponentForm()">Validate Form</button>
                        </div>
                        <div class="output-section">
                            <h3>✅ Generated Component Configuration:</h3>
                            <pre id="component-output">{}</pre>
                        </div>
                    </div>
                </div>

                <!-- Row Configuration Tab -->
                <div class="tab-pane fade" id="row-pane" role="tabpanel">
                    <div class="schema-section">
                        <h2>Row Configuration</h2>
                        <small class="text-muted">Row-specific settings for each data source/table</small>
                        <div class="form-container">
                            <div id="row-editor"></div>
                            <button class="btn-primary" onclick="validateRowForm()">Validate Form</button>
                        </div>
                        <div class="output-section">
                            <h3>✅ Generated Row Configuration:</h3>
                            <pre id="row-output">{}</pre>
                        </div>
                    </div>
                </div>

                <!-- Combined Configuration Tab -->
                <div class="tab-pane fade" id="combined-pane" role="tabpanel">
                    <div class="combined-config">
                        <h3>📦 Complete Component Configuration</h3>
                        <div class="help-text">
                            <strong>💡 How to use:</strong> This is a complete config.json ready to paste into Keboola platform.
                            All component and row parameters are merged into a single <code>parameters</code> object.
                        </div>
                        <button class="btn-success" onclick="copyToClipboard()">📋 Copy to Clipboard</button>
                        <div class="output-section">
                            <h3>✅ Complete config.json</h3>
                            <pre id="combined-output">{}</pre>
                        </div>
                    </div>
                </div>
            </div>
            </div> <!-- end main-content -->
        </div> <!-- end content -->
    </div> <!-- end main-container -->

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let componentEditor, rowEditor;

        // Store for debounce timers
        const watchDebounceTimers = {};

        // ======================================
        // AUTO-LOAD ON PAGE LOAD
        // ======================================

        // Load schemas from /api/schemas on page load
        async function loadSchemas() {
            try {
                const response = await fetch('/api/schemas');
                if (!response.ok) {
                    throw new Error(`Failed to load schemas: ${response.statusText}`);
                }
                const data = await response.json();
                initializeEditors(data.componentSchema, data.rowSchema);

                showStatus('success', '✅ Schemas loaded successfully');
            } catch (error) {
                console.error('Error loading schemas:', error);
                showStatus('error', `❌ Error loading schemas: ${error.message}`);
            }
        }

        // Load config from /api/config and pre-fill editors
        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                const config = await response.json();

                if (Object.keys(config).length > 0) {
                    splitAndFillConfig(config);
                    showStatus('success', '✅ Loaded configuration from data/config.json', true);
                } else {
                    showStatus('info', 'ℹ️  No existing config.json found (starting with empty config)', true);
                }
            } catch (error) {
                console.error('Error loading config:', error);
                // Don't show error, just log it
            }
        }

        // Split combined config into component and row parts
        function splitAndFillConfig(config) {
            if (!componentEditor || !rowEditor) {
                console.warn('Editors not ready yet');
                return;
            }

            // Get property keys from both schemas
            const componentSchema = componentEditor.schema;
            const rowSchema = rowEditor.schema;

            const componentKeys = Object.keys(componentSchema.properties || {});
            const rowKeys = Object.keys(rowSchema.properties || {});

            // Split the parameters
            const componentParams = {};
            const rowParams = {};

            Object.keys(config).forEach(key => {
                if (componentKeys.includes(key)) {
                    componentParams[key] = config[key];
                }
                if (rowKeys.includes(key)) {
                    rowParams[key] = config[key];
                }
            });

            // Pre-fill editors with loaded values
            if (Object.keys(componentParams).length > 0) {
                componentEditor.setValue(componentParams);
                console.log('Pre-filled component config:', componentParams);
            }
            if (Object.keys(rowParams).length > 0) {
                rowEditor.setValue(rowParams);
                console.log('Pre-filled row config:', rowParams);
            }
        }

        // Show status message
        function showStatus(type, message, append = false) {
            const statusDiv = document.getElementById('status');
            const alertClass = type === 'success' ? 'alert-success' :
                              type === 'error' ? 'alert-danger' : 'alert-info';

            const html = `<div class="alert ${alertClass}">${message}</div>`;

            if (append) {
                statusDiv.innerHTML += html;
            } else {
                statusDiv.innerHTML = html;
            }
        }

        // ======================================
        // ASYNC ACTIONS AND WATCH SUPPORT
        // ======================================

        // Call sync action endpoint (hardcoded to /sync-action)
        async function callSyncAction(action, parameters) {
            // Merge component and row configs to create combined parameters
            const combinedParameters = {
                ...componentEditor.getValue(),
                ...parameters
            };

            try {
                const response = await fetch('/sync-action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action, parameters: combinedParameters })
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`HTTP ${response.status}: ${errorText}`);
                }

                return await response.json();
            } catch (error) {
                console.error('Sync action failed:', error);
                throw error;
            }
        }

        // Setup async field (dropdown with load button or auto-load)
        function setupAsyncField(editor, fieldPath, schema, originalSchema) {
            const prop = originalSchema.properties[fieldPath];
            if (!prop || !prop.options?.async) return;

            const asyncOptions = prop.options.async;
            const action = asyncOptions.action;
            const watchFields = asyncOptions.watch || [];
            const autoload = asyncOptions.autoload || false;

            console.log(`Setting up async field: ${fieldPath}, action: ${action}, watch: ${watchFields.join(',')}`);

            // Find the select element
            const fieldEditor = editor.getEditor(`root.${fieldPath}`);
            if (!fieldEditor) {
                console.warn(`Field editor not found for: ${fieldPath}`);
                return;
            }

            // Create load function
            const loadOptions = async () => {
                try {
                    // Show loading state
                    const selectElement = fieldEditor.input;
                    if (selectElement) {
                        selectElement.disabled = true;
                        selectElement.style.opacity = '0.6';
                    }

                    // Get current form values
                    const parameters = editor.getValue();

                    console.log(`Loading options for ${fieldPath} with action ${action}`);
                    const result = await callSyncAction(action, parameters);

                    // Handle different response formats
                    let options = [];
                    if (result.options) {
                        options = result.options;
                    } else if (result.data) {
                        options = result.data;
                    } else if (Array.isArray(result)) {
                        options = result;
                    }

                    console.log(`Received ${options.length} options for ${fieldPath}`);

                    // Update the field's enum with loaded options
                    if (options.length > 0) {
                        // Extract values and labels from options
                        // Options can be either {value, label} objects or plain strings
                        const values = options.map(opt => typeof opt === 'object' ? opt.value : opt);
                        const labels = options.map(opt => typeof opt === 'object' ? opt.label : opt);

                        console.log(`Extracted values:`, values);

                        // Directly update the select element (simpler than JSONEditor API)
                        const selectElement = fieldEditor.input;
                        if (selectElement && selectElement.tagName === 'SELECT') {
                            // Clear existing options
                            selectElement.innerHTML = '';

                            // Add empty option if field is not required
                            if (!prop.required) {
                                const emptyOption = document.createElement('option');
                                emptyOption.value = '';
                                emptyOption.text = '-- Select --';
                                selectElement.appendChild(emptyOption);
                            }

                            // Add new options
                            values.forEach((value, index) => {
                                const option = document.createElement('option');
                                option.value = value;
                                option.text = labels[index];
                                selectElement.appendChild(option);
                            });

                            console.log(`✅ Populated dropdown with ${values.length} options`);
                        } else {
                            console.warn('Field is not a select element, cannot populate options');
                        }
                    }

                    // Restore UI
                    if (selectElement) {
                        selectElement.disabled = false;
                        selectElement.style.opacity = '1';
                    }

                } catch (error) {
                    console.error(`Error loading options for ${fieldPath}:`, error);
                    alert(`Failed to load options for ${prop.title || fieldPath}:\\n${error.message}`);

                    // Restore UI
                    const selectElement = fieldEditor.input;
                    if (selectElement) {
                        selectElement.disabled = false;
                        selectElement.style.opacity = '1';
                    }
                }
            };

            // Setup watch listeners if specified
            if (watchFields.length > 0) {
                watchFields.forEach(watchField => {
                    const watchFieldPath = `root.${watchField}`;

                    // Watch for changes on the watched field
                    editor.watch(watchFieldPath, () => {
                        // Clear existing debounce timer
                        const timerKey = `${fieldPath}_${watchField}`;
                        if (watchDebounceTimers[timerKey]) {
                            clearTimeout(watchDebounceTimers[timerKey]);
                        }

                        // Set new debounce timer (1 second)
                        watchDebounceTimers[timerKey] = setTimeout(() => {
                            console.log(`Watch triggered: ${watchField} changed, reloading ${fieldPath}`);
                            loadOptions();
                        }, 1000);
                    });
                });

                console.log(`Watch listeners setup for ${fieldPath} on fields: ${watchFields.join(', ')}`);
            }

            // Auto-load if specified
            if (autoload) {
                // Give the editor time to fully initialize
                setTimeout(() => {
                    console.log(`Auto-loading options for ${fieldPath}`);
                    loadOptions();
                }, 500);
            }

            // Add manual load button
            const container = fieldEditor.container;
            if (container) {
                // Check if button already exists
                if (!container.querySelector('.async-load-btn')) {
                    const loadButton = document.createElement('button');
                    loadButton.className = 'btn-primary async-load-btn';
                    loadButton.textContent = `🔄 ${asyncOptions.label || 'Load Options'}`;
                    loadButton.style.marginTop = '10px';
                    loadButton.style.fontSize = '0.9rem';
                    loadButton.style.padding = '8px 16px';

                    loadButton.onclick = async (e) => {
                        e.preventDefault();
                        await loadOptions();
                    };

                    container.appendChild(loadButton);
                }
            }
        }

        // Setup watch listeners for all async fields in the schema
        function setupWatchListeners(editor, schema, originalSchema, parentPath = '') {
            if (!schema.properties) return;

            Object.keys(schema.properties).forEach(fieldName => {
                const fieldPath = parentPath ? `${parentPath}.${fieldName}` : fieldName;
                const prop = originalSchema.properties[fieldName];

                // Check if field has async options
                if (prop && prop.format === 'select' && prop.options?.async) {
                    setupAsyncField(editor, fieldPath, schema, originalSchema);
                }

                // Recursively handle nested objects
                if (prop && prop.type === 'object' && prop.properties) {
                    setupWatchListeners(editor, prop, prop, fieldPath);
                }
            });
        }

        // Setup action buttons (for button type fields)
        function setupActionButtons(editor, schema, originalSchema, parentPath = '') {
            if (!schema.properties) return;

            Object.keys(schema.properties).forEach(fieldName => {
                const fieldPath = parentPath ? `${parentPath}.${fieldName}` : fieldName;
                const processedProp = schema.properties[fieldName];
                const originalProp = originalSchema.properties[fieldName];

                // Check if this is a button field
                if (originalProp && originalProp.type === 'button' && processedProp.options?._isButton) {
                    const action = processedProp.options._action;
                    const label = processedProp.options._label;

                    console.log(`Setting up button: ${fieldPath}, action: ${action}, label: ${label}`);

                    // Find the field editor container
                    const fieldEditor = editor.getEditor(`root.${fieldPath}`);
                    if (fieldEditor && fieldEditor.container) {
                        console.log(`Found field editor for ${fieldPath}`);

                        // Hide the input element (it's already hidden via CSS but double-check)
                        const inputElement = fieldEditor.input;
                        if (inputElement) {
                            inputElement.style.display = 'none';
                        }

                        // Hide the label too (makes it cleaner)
                        const labelElement = fieldEditor.container.querySelector('label');
                        if (labelElement) {
                            labelElement.style.display = 'none';
                        }

                        // Create action button
                        if (!fieldEditor.container.querySelector('.sync-action-btn')) {
                            const button = document.createElement('button');
                            button.className = 'btn-primary sync-action-btn';
                            button.textContent = `🔘 ${label}`;
                            button.style.width = '100%';
                            button.style.marginTop = '10px';
                            button.style.padding = '12px';
                            button.style.fontSize = '0.95rem';
                            button.style.background = '#1BC98E';
                            button.style.border = 'none';
                            button.style.borderRadius = '4px';
                            button.style.color = 'white';
                            button.style.cursor = 'pointer';
                            button.style.fontWeight = '600';

                            button.onclick = async (e) => {
                                e.preventDefault();
                                await executeSyncAction(editor, action, label);
                            };

                            fieldEditor.container.appendChild(button);
                            console.log(`✅ Button created for ${fieldPath}`);
                        }
                    } else {
                        console.warn(`Could not find field editor for: ${fieldPath}`);
                    }
                }

                // Recursively handle nested objects
                if (originalProp && originalProp.type === 'object' && originalProp.properties) {
                    console.log(`Recursing into nested object: ${fieldPath}`);
                    setupActionButtons(editor, processedProp, originalProp, fieldPath);
                }
            });
        }

        // Execute a sync action and show results
        async function executeSyncAction(editor, action, label) {
            try {
                const button = event.target;
                button.disabled = true;
                button.style.opacity = '0.6';
                button.textContent = `⏳ ${label}...`;

                // Get current form values (combined config)
                const componentConfig = componentEditor ? componentEditor.getValue() : {};
                const rowConfig = editor.getValue();
                const parameters = {...componentConfig, ...rowConfig};

                // Call sync action
                const result = await callSyncAction(action, parameters);

                // Show result in alert/modal
                if (result.status === 'success' || !result.status) {
                    alert(`✅ ${label} succeeded!\\n\\n${JSON.stringify(result, null, 2)}`);
                } else {
                    alert(`❌ ${label} failed:\\n\\n${result.message || JSON.stringify(result, null, 2)}`);
                }

                button.disabled = false;
                button.style.opacity = '1';
                button.textContent = `🔘 ${label}`;
            } catch (error) {
                const button = event.target;
                button.disabled = false;
                button.style.opacity = '1';
                button.textContent = `🔘 ${label}`;

                alert(`❌ ${label} error:\\n\\n${error.message}`);
                console.error('Sync action error:', error);
            }
        }

        // ======================================
        // SCHEMA PREPROCESSING
        // ======================================

        // Preprocess schema to handle Keboola-specific features
        function preprocessSchema(schema) {
            const processed = JSON.parse(JSON.stringify(schema)); // Deep clone

            if (processed.properties) {
                Object.keys(processed.properties).forEach(key => {
                    const prop = processed.properties[key];

                    // Handle button type (not standard JSON Schema)
                    if (prop.type === 'button') {
                        const action = prop.options?.async?.action || 'unknown';
                        const label = prop.options?.async?.label || prop.title || 'Button';

                        // Convert button to a string field (we'll hide input and add real button via DOM)
                        processed.properties[key] = {
                            type: 'string',
                            title: prop.title || label,
                            default: '',
                            options: {
                                _isButton: true,  // Mark for button creation
                                _action: action,
                                _label: label,
                                inputAttributes: {
                                    style: 'display: none;'  // Hide the input
                                }
                            },
                            propertyOrder: prop.propertyOrder
                        };
                    }

                    // Handle async selects - keep them as selects (not readonly)
                    if (prop.format === 'select' && prop.options?.async) {
                        // Mark this field as having async loading
                        if (!prop.options) prop.options = {};
                        prop.options._hasAsync = true;
                    }

                    // Ensure multiselect arrays work properly
                    if (prop.type === 'array' && prop.format === 'select') {
                        // JSONEditor needs these options for multiselect
                        if (!prop.options) prop.options = {};
                        prop.uniqueItems = true;
                    }
                });
            }

            return processed;
        }

        // Store original schemas for async field setup
        let originalComponentSchema = null;
        let originalRowSchema = null;

        // Initialize editors with schemas
        function initializeEditors(componentSchema, rowSchema) {
            // Store original schemas
            originalComponentSchema = componentSchema;
            originalRowSchema = rowSchema;

            // Preprocess schemas to handle Keboola-specific features
            const processedComponentSchema = preprocessSchema(componentSchema);
            const processedRowSchema = preprocessSchema(rowSchema);

            // Initialize Component Editor
            if (componentEditor) componentEditor.destroy();
            const componentElement = document.getElementById('component-editor');
            componentEditor = new JSONEditor(componentElement, {
                schema: processedComponentSchema,
                theme: 'bootstrap5',
                iconlib: 'bootstrap',
                disable_collapse: false,
                disable_edit_json: false,
                disable_properties: false,
                show_errors: 'interaction',
                prompt_before_delete: false,
                no_additional_properties: false,
                required_by_default: false,
                keep_oneof_values: false,
                use_default_values: true,
                select2: {
                    tags: true,
                    width: '100%'
                }
            });

            componentEditor.on('ready', function() {
                componentEditor.on('change', function() {
                    updateComponentOutput();
                    updateCombinedOutput();
                });
                setTimeout(() => {
                    updateComponentOutput();
                    // Setup async fields and watch listeners
                    setupWatchListeners(componentEditor, processedComponentSchema, originalComponentSchema);
                    // Setup action buttons
                    setupActionButtons(componentEditor, processedComponentSchema, originalComponentSchema);
                }, 100);
            });

            // Initialize Row Editor
            if (rowEditor) rowEditor.destroy();
            const rowElement = document.getElementById('row-editor');
            rowEditor = new JSONEditor(rowElement, {
                schema: processedRowSchema,
                theme: 'bootstrap5',
                iconlib: 'bootstrap',
                disable_collapse: false,
                disable_edit_json: false,
                disable_properties: false,
                show_errors: 'interaction',
                prompt_before_delete: false,
                no_additional_properties: false,
                required_by_default: false,
                keep_oneof_values: false,
                use_default_values: true,
                select2: {
                    tags: true,
                    width: '100%'
                }
            });

            rowEditor.on('ready', function() {
                rowEditor.on('change', function() {
                    updateRowOutput();
                    updateCombinedOutput();
                });
                setTimeout(() => {
                    updateRowOutput();
                    updateCombinedOutput();
                    // Setup async fields and watch listeners
                    setupWatchListeners(rowEditor, processedRowSchema, originalRowSchema);
                    // Setup action buttons
                    setupActionButtons(rowEditor, processedRowSchema, originalRowSchema);
                }, 100);
            });
        }

        // Handle folder selection
        function handleFolderSelect(event) {
            const files = event.target.files;
            if (files.length > 0) {
                // Get the path from the first file (folder path)
                const firstFile = files[0];
                const folderPath = firstFile.webkitRelativePath.split('/')[0];
                // Set the full path in the input
                document.getElementById('manual-component-config').value = folderPath;
            }
        }

        // Handle file selection
        function handleFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                document.getElementById('manual-config-json').value = file.name;
            }
        }

        // Reload schemas (using manual paths if set, otherwise auto-discovery)
        async function reloadSchemas() {
            document.getElementById('status').innerHTML = '';

            const componentConfigPath = document.getElementById('manual-component-config').value.trim();
            const configJsonPath = document.getElementById('manual-config-json').value.trim();

            try {
                // Load schemas (with optional manual path)
                let schemaUrl = '/api/schemas';
                if (componentConfigPath) {
                    schemaUrl += `?path=${encodeURIComponent(componentConfigPath)}`;
                }

                const schemaResponse = await fetch(schemaUrl);
                if (!schemaResponse.ok) {
                    throw new Error(`Failed to load schemas: ${schemaResponse.statusText}`);
                }
                const schemaData = await schemaResponse.json();
                initializeEditors(schemaData.componentSchema, schemaData.rowSchema);

                showStatus('success', '✅ Schemas loaded successfully');

                // Load config (with optional manual path)
                let configUrl = '/api/config';
                if (configJsonPath) {
                    configUrl += `?path=${encodeURIComponent(configJsonPath)}`;
                }

                const configResponse = await fetch(configUrl);
                if (configResponse.ok) {
                    const config = await configResponse.json();
                    if (Object.keys(config).length > 0) {
                        setTimeout(() => {
                            splitAndFillConfig(config);
                            showStatus('success', '✅ Configuration loaded', true);
                        }, 500);
                    }
                }
            } catch (error) {
                console.error('Error reloading schemas:', error);
                showStatus('error', `❌ Error: ${error.message}`);
            }
        }

        // Update outputs
        function updateComponentOutput() {
            if (!componentEditor || !componentEditor.ready) return;

            const output = document.getElementById('component-output');
            const errors = componentEditor.validate();

            if (errors.length === 0) {
                output.textContent = JSON.stringify(componentEditor.getValue(), null, 2);
                output.style.borderColor = '#1BC98E';
            } else {
                output.textContent = JSON.stringify(componentEditor.getValue(), null, 2) +
                    '\\n\\n// ERRORS:\\n' + JSON.stringify(errors, null, 2);
                output.style.borderColor = '#dc3545';
            }
        }

        function updateRowOutput() {
            if (!rowEditor || !rowEditor.ready) return;

            const output = document.getElementById('row-output');
            const errors = rowEditor.validate();

            if (errors.length === 0) {
                output.textContent = JSON.stringify(rowEditor.getValue(), null, 2);
                output.style.borderColor = '#1BC98E';
            } else {
                output.textContent = JSON.stringify(rowEditor.getValue(), null, 2) +
                    '\\n\\n// ERRORS:\\n' + JSON.stringify(errors, null, 2);
                output.style.borderColor = '#dc3545';
            }
        }

        function updateCombinedOutput() {
            if (!componentEditor || !componentEditor.ready || !rowEditor || !rowEditor.ready) return;

            const combined = {
                parameters: {
                    ...componentEditor.getValue(),
                    ...rowEditor.getValue()
                }
            };

            document.getElementById('combined-output').textContent =
                JSON.stringify(combined, null, 2);
        }

        // Copy to clipboard
        function copyToClipboard() {
            const text = document.getElementById('combined-output').textContent;
            navigator.clipboard.writeText(text).then(() => {
                alert('✅ Copied to clipboard!');
            }).catch(err => {
                alert('❌ Failed to copy: ' + err);
            });
        }

        // Validate forms
        function validateComponentForm() {
            const errors = componentEditor.validate();
            if (errors.length === 0) {
                alert('✅ Component configuration is valid!');
            } else {
                alert('❌ Validation errors:\\n\\n' + errors.map(e => `${e.path}: ${e.message}`).join('\\n'));
            }
        }

        function validateRowForm() {
            const errors = rowEditor.validate();
            if (errors.length === 0) {
                alert('✅ Row configuration is valid!');
            } else {
                alert('❌ Validation errors:\\n\\n' + errors.map(e => `${e.path}: ${e.message}`).join('\\n'));
            }
        }

        // Initialize on page load
        // Pre-fill manual input fields with auto-discovered paths
        async function loadDiscoveryInfo() {
            try {
                const response = await fetch('/api/discovery-info');
                if (response.ok) {
                    const info = await response.json();
                    if (info.componentConfig) {
                        document.getElementById('manual-component-config').value = info.componentConfig;
                    }
                    if (info.configJson) {
                        document.getElementById('manual-config-json').value = info.configJson;
                    }
                }
            } catch (error) {
                console.warn('Could not load discovery info:', error);
            }
        }

        window.addEventListener('DOMContentLoaded', () => {
            loadDiscoveryInfo();  // Pre-fill manual paths
            loadSchemas();
            // Wait for editors to initialize, then load config
            setTimeout(loadConfig, 500);
        });
    </script>
</body>
</html>
"""


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    # Auto-discover project structure
    project_root = find_project_root()

    if not project_root:
        print("\n" + "="*80)
        print("❌ ERROR: Could not find component_config/ folder")
        print("="*80)
        print("\nPlease run this script from within your component project directory,")
        print("or ensure a component_config/ folder exists in a parent directory.")
        print("="*80 + "\n")
        sys.exit(1)

    component_config_path = find_component_config(project_root)
    config_json_path = find_config_json(project_root)

    # Verify required schemas exist
    if not os.path.exists(os.path.join(component_config_path, 'configSchema.json')):
        print(f"\n❌ ERROR: configSchema.json not found in {component_config_path}")
        sys.exit(1)

    if not os.path.exists(os.path.join(component_config_path, 'configRowSchema.json')):
        print(f"\n❌ ERROR: configRowSchema.json not found in {component_config_path}")
        sys.exit(1)

    # Print startup information
    print("\n" + "="*80)
    print("🏭 KEBOOLA COMPONENT SCHEMA TESTER")
    print("="*80)
    print(f"✅ Project root:       {project_root}")
    print(f"✅ Component config:   {component_config_path}")

    if config_json_path:
        print(f"✅ Config.json:        {config_json_path}")
    else:
        print(f"ℹ️  Config.json:        Not found (will use empty config)")

    print("\n" + "-"*80)
    print("🚀 Starting server on http://localhost:8000")
    print("-"*80)
    print("\nPress Ctrl+C to stop the server")
    print("="*80 + "\n")

    # Set up environment for component imports
    os.environ['KBC_DATADIR'] = os.path.join(project_root, 'data')
    sys.path.insert(0, os.path.join(project_root, 'src'))

    # Start Flask server
    try:
        app.run(host='0.0.0.0', port=8000, debug=False)
    except KeyboardInterrupt:
        print("\n\n" + "="*80)
        print("👋 Server stopped")
        print("="*80 + "\n")
        sys.exit(0)
