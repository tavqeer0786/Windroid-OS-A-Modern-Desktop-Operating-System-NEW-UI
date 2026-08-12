import { StorageProvider, StorageDeviceEvent } from './StorageProvider';
import { SystemDrive } from '../models/drive';
import { FileEntry, FileInfo } from '../models/file-entry';

export class NativeLinuxStorageProvider implements StorageProvider {
  public id = 'native-linux-storage-provider';
  public name = 'Native Windroid Linux Storage Service';
  public isNative = true;

  private get bridge() {
    if (typeof window !== 'undefined') {
      if (window.windroid?.storage) return window.windroid.storage;
      if (window.aether?.storage) return window.aether.storage;
    }
    return null;
  }

  public isAvailable(): boolean {
    return this.bridge !== null;
  }

  public async getDrives(): Promise<SystemDrive[]> {
    if (!this.bridge) {
      throw new Error('Native Linux Storage Bridge (Windroid D-Bus Service) is not available in this environment.');
    }
    return await this.bridge.getDrives();
  }

  public async getDrive(id: string): Promise<SystemDrive | null> {
    if (!this.bridge) {
      throw new Error('Native Linux Storage Bridge is unavailable.');
    }
    return await this.bridge.getDrive(id);
  }

  public async listDirectory(path: string): Promise<FileEntry[]> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.listDirectory(path);
  }

  public async getFileInfo(path: string): Promise<FileInfo> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.getFileInfo(path);
  }

  public async createFolder(path: string, name: string): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.createFolder(path, name);
  }

  public async createFile(path: string, name: string): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.createFile(path, name);
  }

  public async rename(path: string, newName: string): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.rename(path, newName);
  }

  public async copy(sources: string[], destination: string): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.copy(sources, destination);
  }

  public async move(sources: string[], destination: string): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.move(sources, destination);
  }

  public async delete(paths: string[], permanent = false): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.delete(paths, permanent);
  }

  public async mount(deviceId: string): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.mount(deviceId);
  }

  public async unmount(deviceId: string): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.unmount(deviceId);
  }

  public async eject(deviceId: string): Promise<void> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    return await this.bridge.eject(deviceId);
  }

  public async unlock(deviceId: string, password?: string): Promise<boolean> {
    if (!this.bridge) throw new Error('Native Linux Storage Bridge is unavailable.');
    if (this.bridge.unlock) {
      return await this.bridge.unlock(deviceId, password);
    }
    return false;
  }

  public subscribeToDeviceChanges(callback: (event: StorageDeviceEvent) => void): () => void {
    if (!this.bridge) {
      return () => {};
    }
    return this.bridge.subscribe(callback);
  }
}
