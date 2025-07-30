import { io, Socket } from "socket.io-client";

let socket: Socket | null = null;

export const initializeSocket = () => {
  if (socket) {
    return socket;
  }

  // Use WebSocket endpoint from the FastAPI backend
  const wsUrl = `ws://${window.location.host}/ws`;
  
  // For development, handle WebSocket connection gracefully
  try {
    socket = io(wsUrl, {
      transports: ['websocket'],
      upgrade: true,
      autoConnect: true,
    });

    socket.on('connect', () => {
      console.log('Connected to DaLeoBanks WebSocket');
    });

    socket.on('disconnect', () => {
      console.log('Disconnected from DaLeoBanks WebSocket');
    });

    socket.on('connect_error', (error) => {
      console.warn('WebSocket connection error:', error);
    });

    return socket;
  } catch (error) {
    console.warn('WebSocket not available, using polling fallback');
    return null;
  }
};

export const getSocket = () => {
  return socket || initializeSocket();
};

export const disconnectSocket = () => {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
};

// Event handlers for real-time updates
export const subscribeToUpdates = (callback: (data: any) => void) => {
  const ws = getSocket();
  if (ws) {
    ws.on('live_mode_changed', callback);
    ws.on('goal_mode_changed', callback);
    ws.on('proposal_generated', callback);
    ws.on('note_added', callback);
    ws.on('persona_updated', callback);
    ws.on('persona_rolled_back', callback);
  }
};

export const unsubscribeFromUpdates = (callback: (data: any) => void) => {
  const ws = getSocket();
  if (ws) {
    ws.off('live_mode_changed', callback);
    ws.off('goal_mode_changed', callback);
    ws.off('proposal_generated', callback);
    ws.off('note_added', callback);
    ws.off('persona_updated', callback);
    ws.off('persona_rolled_back', callback);
  }
};
