# SOC Copilot UI Architecture

## Component Hierarchy

```
MainWindow (main_window.py)
├── Sidebar
│   ├── Logo/Title
│   ├── Quick Stats Card
│   │   ├── Alert Counter (animated)
│   │   └── Results Counter (animated)
│   ├── Navigation Buttons (5)
│   │   ├── Dashboard (Ctrl+1)
│   │   ├── Alerts (Ctrl+2)
│   │   ├── Investigation (Ctrl+3)
│   │   ├── Assistant (Ctrl+4)
│   │   └── Settings (Ctrl+,)
│   └── Status Indicator
│
├── Content Area
│   ├── SystemStatusBar (always visible)
│   │   ├── Pipeline LED
│   │   ├── Ingestion LED
│   │   ├── Kill Switch LED
│   │   ├── Admin LED
│   │   ├── Buffer LED
│   │   └── Results Counter
│   │
│   ├── Banners (conditional)
│   │   ├── KillSwitchBanner
│   │   └── PermissionBanner
│   │
│   └── PageStack (5 pages)
│       ├── Page 0: Dashboard
│       │   ├── Header (title + buttons)
│       │   ├── Metric Cards (4)
│       │   ├── Status Cards (2)
│       │   ├── Progress Bar
│       │   └── Activity Feed
│       │
│       ├── Page 1: AlertsView ⭐ OPTIMIZED
│       │   ├── Header
│       │   │   ├── Title + Counter
│       │   │   ├── Priority Filter
│       │   │   ├── Search Box
│       │   │   └── Refresh Button
│       │   ├── Table (200 alerts)
│       │   │   ├── Incremental Updates (2s)
│       │   │   ├── Scroll Preservation
│       │   │   └── Batch Rendering
│       │   └── Empty State
│       │
│       ├── Page 2: AlertDetailsPanel ⭐ REDESIGNED
│       │   ├── Header
│       │   │   ├── Back Button
│       │   │   └── Title
│       │   ├── Priority Badge
│       │   ├── Classification Header
│       │   ├── Metric Cards (3)
│       │   ├── Network Cards (2)
│       │   ├── Metadata Cards (2)
│       │   ├── Reasoning Section
│       │   └── Action Section
│       │
│       ├── Page 3: AssistantPanel
│       │   └── (unchanged)
│       │
│       └── Page 4: ConfigPanel
│           └── (unchanged)
│
└── StatusBar (bottom)
    └── Real-time status text
```

## Data Flow

```
ControllerBridge (read-only)
    ↓
    ├─→ Sidebar (1s polling)
    │   └─→ Animated Counters
    │
    ├─→ SystemStatusBar (1s polling)
    │   └─→ LED Indicators
    │
    ├─→ Dashboard (1.5s polling)
    │   ├─→ Metric Cards
    │   ├─→ Status Cards
    │   └─→ Activity Feed
    │
    ├─→ AlertsView (2s incremental)
    │   ├─→ Alert Cache
    │   ├─→ Filter Engine (client-side)
    │   └─→ Table Renderer
    │
    └─→ AlertDetailsPanel (on-demand)
        └─→ Card Renderer
```

## Update Cycles

```
1 second:  SystemStatusBar → LED updates
1 second:  Sidebar → Counter animation
1.5 seconds: Dashboard → Metrics refresh
2 seconds:  AlertsView → Incremental check
On-demand: AlertDetailsPanel → Load on click
```

## Performance Optimizations

```
AlertsView Rendering Pipeline:
┌─────────────────────────────────────┐
│ 1. Fetch alerts (limit=200)        │
│    ↓                                │
│ 2. Check cache for new alerts      │
│    ↓                                │
│ 3. If new: Update cache             │
│    ↓                                │
│ 4. Apply filters (client-side)     │
│    ↓                                │
│ 5. Save scroll position             │
│    ↓                                │
│ 6. Disable table updates            │
│    ↓                                │
│ 7. Batch render rows                │
│    ↓                                │
│ 8. Enable table updates (repaint)   │
│    ↓                                │
│ 9. Restore scroll position          │
└─────────────────────────────────────┘
```

## Navigation Flow

```
User Actions → Navigation
├── Click sidebar button → PageStack.setCurrentIndex()
├── Press Ctrl+1-4 → PageStack.setCurrentIndex()
├── Click alert row → Navigate to Investigation
├── Click back button → Navigate to Alerts
└── Press F5 → Refresh current view
```

## Color Coding System

```
Priority Colors:
├── Critical: #ff4444 (Red)
├── High:     #ff8800 (Orange)
├── Medium:   #ffaa00 (Yellow)
└── Low:      #ffffff (White)

Status Colors:
├── Active/Success:  #4CAF50 (Green)
├── Processing:      #2196F3 (Blue)
├── Warning:         #ffa000 (Amber)
├── Error/Critical:  #ff4444 (Red)
└── Inactive:        #757575 (Gray)

UI Accent:
└── Primary: #00d4ff (Cyan)
```

## Keyboard Shortcuts Map

```
Ctrl+1 → Dashboard
Ctrl+2 → Alerts
Ctrl+3 → Investigation
Ctrl+4 → Assistant
Ctrl+, → Settings
F5     → Refresh current view
```

## Component Communication

```
MainWindow
    ↓ (signal: nav_changed)
Sidebar → PageStack.setCurrentIndex()

AlertsView
    ↓ (signal: alert_selected)
MainWindow → Navigate to Investigation
           → Update AlertDetailsPanel

AlertDetailsPanel
    ↓ (signal: back_clicked)
MainWindow → Navigate to Alerts
```

## Optimization Summary

```
Component          | Optimization Applied
-------------------|---------------------
AlertsView         | Incremental updates, caching, batch rendering
AlertDetailsPanel  | Card-based layout, color coding
MainWindow         | Keyboard shortcuts, navigation sync
Sidebar            | Animated counters, real-time polling
SystemStatusBar    | 1-second updates (already optimal)
Dashboard          | Activity feed, animated cards (already optimal)
```
