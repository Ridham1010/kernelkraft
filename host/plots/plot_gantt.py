#!/usr/bin/env python3
"""
Gantt chart plotter for xv6 trace ring output.
Parses schedtrace output and creates a PNG with:
- One lane per CPU
- Horizontal bars per process interval (SWITCH_IN to SWITCH_OUT)
- Vertical markers for DONATE (red), WITHDRAW (blue), CYCLE (yellow), DEADLINE_MISS (black)
"""
import sys
import re
import argparse
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    print("matplotlib not installed. Install with: pip3 install matplotlib")
    sys.exit(1)

# Event types from sched_api.h
TRACE_SWITCH_IN = 1
TRACE_SWITCH_OUT = 2
TRACE_DONATE = 3
TRACE_WITHDRAW = 4
TRACE_CYCLE = 5
TRACE_DEADLINE_MISS = 6

EVENT_NAMES = {
    TRACE_SWITCH_IN: 'SWITCH_IN',
    TRACE_SWITCH_OUT: 'SWITCH_OUT',
    TRACE_DONATE: 'DONATE',
    TRACE_WITHDRAW: 'WITHDRAW',
    TRACE_CYCLE: 'CYCLE',
    TRACE_DEADLINE_MISS: 'DEADLINE_MISS',
}

EVENT_COLORS = {
    TRACE_SWITCH_IN: 'green',
    TRACE_SWITCH_OUT: 'red',
    TRACE_DONATE: 'red',
    TRACE_WITHDRAW: 'blue',
    TRACE_CYCLE: 'gold',
    TRACE_DEADLINE_MISS: 'black',
}

EVENT_MARKERS = {
    TRACE_DONATE: '^',      # triangle up
    TRACE_WITHDRAW: 'v',    # triangle down
    TRACE_CYCLE: '*',       # star
    TRACE_DEADLINE_MISS: 'X',  # X mark
}


def parse_schedtrace_output(lines):
    """Parse schedtrace output lines into list of events."""
    events = []
    # Format: tlo thi cpu pid ev arg seq
    pattern = re.compile(
        r'^(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+'
        r'(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(\d+)$'
    )
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = pattern.match(line)
        if m:
            tlo = int(m.group(1), 16)
            thi = int(m.group(2), 16)
            cpu = int(m.group(3))
            pid = int(m.group(4))
            ev = int(m.group(5))
            arg = int(m.group(6))
            seq = int(m.group(7))
            events.append({
                'tlo': tlo, 'thi': thi, 'cpu': cpu, 'pid': pid,
                'ev': ev, 'arg': arg, 'seq': seq
            })
    return events


def reconstruct_intervals(events):
    """Reconstruct process execution intervals from SWITCH_IN/OUT events."""
    # Per-CPU: track current running process
    cpu_current = {}
    # Per-CPU: list of (pid, start_seq, end_seq, start_tlo, end_tlo)
    cpu_intervals = defaultdict(list)
    # For cross-CPU ordering, use global seq
    
    for e in events:
        cpu = e['cpu']
        pid = e['pid']
        ev = e['ev']
        seq = e['seq']
        
        if ev == TRACE_SWITCH_IN:
            # New process starts running
            cpu_current[cpu] = {'pid': pid, 'start_seq': seq, 'start_tlo': e['tlo']}
        elif ev == TRACE_SWITCH_OUT:
            # Process stops running
            if cpu in cpu_current and cpu_current[cpu]['pid'] == pid:
                start_info = cpu_current[cpu]
                cpu_intervals[cpu].append({
                    'pid': pid,
                    'start_seq': start_info['start_seq'],
                    'end_seq': seq,
                    'start_tlo': start_info['start_tlo'],
                    'end_tlo': e['tlo'],
                })
                del cpu_current[cpu]
    
    return cpu_intervals


def plot_gantt(events, output_file, title="xv6 Scheduler Trace"):
    """Create Gantt chart from events."""
    cpu_intervals = reconstruct_intervals(events)
    
    # Collect all marker events (non-switch events)
    marker_events = [e for e in events if e['ev'] not in (TRACE_SWITCH_IN, TRACE_SWITCH_OUT)]
    
    # Determine CPUs and PIDs
    cpus = sorted(set(e['cpu'] for e in events))
    pids = sorted(set(e['pid'] for e in events if e['pid'] > 0))
    
    # Color map for PIDs
    import matplotlib.cm as cm
    pid_colors = {}
    for i, pid in enumerate(pids):
        pid_colors[pid] = cm.tab20(i % 20)
    
    fig, ax = plt.subplots(figsize=(14, 2 + len(cpus) * 0.8))
    
    # Plot intervals
    y_positions = {cpu: i for i, cpu in enumerate(cpus)}
    bar_height = 0.6
    
    for cpu in cpus:
        y = y_positions[cpu]
        for interval in cpu_intervals.get(cpu, []):
            pid = interval['pid']
            start = interval['start_seq']
            end = interval['end_seq']
            color = pid_colors.get(pid, 'gray')
            ax.barh(y, end - start, left=start, height=bar_height,
                    color=color, edgecolor='black', linewidth=0.5,
                    label=f'PID {pid}' if pid not in ax.get_legend_handles_labels()[1] else '')
            # Add PID label in the middle if bar is wide enough
            if end - start > 50:
                ax.text((start + end) / 2, y, str(pid),
                       ha='center', va='center', fontsize=8, color='white', fontweight='bold')
    
    # Plot markers
    for e in marker_events:
        cpu = e['cpu']
        if cpu not in y_positions:
            continue
        y = y_positions[cpu]
        seq = e['seq']
        ev = e['ev']
        marker = EVENT_MARKERS.get(ev, 'o')
        color = EVENT_COLORS.get(ev, 'black')
        label = EVENT_NAMES.get(ev, str(ev))
        
        ax.plot(seq, y, marker=marker, color=color, markersize=10,
                label=label if label not in ax.get_legend_handles_labels()[1] else '')
        
        # Add annotation for DONATE/WITHDRAW with arg (deadline)
        if ev in (TRACE_DONATE, TRACE_WITHDRAW) and e['arg'] > 0:
            ax.annotate(f"dl={e['arg']}", (seq, y),
                       xytext=(5, 15), textcoords='offset points',
                       fontsize=7, color=color, ha='left')
    
    # Formatting
    ax.set_yticks(list(y_positions.values()))
    ax.set_yticklabels([f'CPU {cpu}' for cpu in cpus])
    ax.set_xlabel('Global Sequence Number (seq)')
    ax.set_title(title)
    ax.grid(True, axis='x', alpha=0.3)
    
    # Legend - only unique labels
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc='upper right', fontsize=8, ncol=2)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close()
    print(f"Gantt chart saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Plot Gantt chart from schedtrace output')
    parser.add_argument('input', nargs='?', help='Input file (default: stdin)')
    parser.add_argument('-o', '--output', default='gantt.png', help='Output PNG file')
    parser.add_argument('-t', '--title', default='xv6 Scheduler Trace', help='Chart title')
    args = parser.parse_args()
    
    if args.input:
        with open(args.input, 'r') as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()
    
    events = parse_schedtrace_output(lines)
    if not events:
        print("No events parsed from input")
        sys.exit(1)
    
    print(f"Parsed {len(events)} events")
    print(f"CPUs: {sorted(set(e['cpu'] for e in events))}")
    print(f"PIDs: {sorted(set(e['pid'] for e in events if e['pid'] > 0))}")
    
    plot_gantt(events, args.output, args.title)


if __name__ == '__main__':
    main()
