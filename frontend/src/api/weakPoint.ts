import api from './index'

export const weakPointApi = {
  getRecommendations: (userId: string, limit = 10) =>
    api.get('/weak-points/recommendations', { params: { user_id: userId, limit } }),

  listAll: (userId: string, status?: string) =>
    api.get('/weak-points', { params: { user_id: userId, status } }),

  updateStatus: (id: number, status: string, userId: string) =>
    api.patch(`/weak-points/${id}/status`, null, { params: { user_id: userId, status } }),

  delete: (id: number, userId: string) =>
    api.delete(`/weak-points/${id}`, { params: { user_id: userId } }),
}
