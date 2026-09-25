import React, { createContext, useContext, useState, useEffect } from 'react';
import { User } from '../types/index.js';
import { api, getActiveUserId, setActiveUserId } from '../api/client.js';

interface AuthContextType {
  currentUser: User | null;
  users: User[];
  switchUser: (userId: string) => void;
  isAdmin: boolean;
  isViewer: boolean;
  canEdit: boolean;
  refreshUsers: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [users, setUsers] = useState<User[]>([]);
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  const fetchUsers = async () => {
    try {
      const data = await api.getUsers();
      setUsers(data);
      const localAdmin = data.find((u: User) => u.id === 'u_admin' && u.role === 'Admin');
      const admin = data.find((u: User) => u.role === 'Admin');
      const activeId = getActiveUserId();
      const rememberedAdmin = data.find((u: User) => u.id === activeId && u.role === 'Admin');
      // This local workspace starts in an administrator session so project
      // creation and configuration are available immediately. Persona
      // switching still works for permission testing until the next reload.
      const current = localAdmin
        || rememberedAdmin
        || admin
        || data[0];
      if (current) {
        setCurrentUser(current);
        setActiveUserId(current.id);
      }
    } catch (e) {
      console.error('Failed to load users:', e);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const switchUser = (userId: string) => {
    const user = users.find(u => u.id === userId);
    if (user) {
      setCurrentUser(user);
      setActiveUserId(user.id);
    }
  };

  const isAdmin = currentUser?.role === 'Admin';
  const isViewer = currentUser?.role === 'Viewer';
  const canEdit = !isViewer;

  return (
    <AuthContext.Provider
      value={{
        currentUser,
        users,
        switchUser,
        isAdmin,
        isViewer,
        canEdit,
        refreshUsers: fetchUsers,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
};

