// This file is no longer used as we're using SQLite with SQLAlchemy
// All storage is handled by the Python backend
export interface IStorage {}
export class MemStorage implements IStorage {}
export const storage = new MemStorage();
