from bridge.qemu_bridge import QemuBridge


def main():
    bridge = QemuBridge()
    bridge.start()
    try:
        print(bridge.run_raw("ls"))
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
