import { api } from '../api/client';

describe('api client', () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  it('getTickets returns an array of tickets', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => [
        { id: '1', title: 'Task A', status: 'pending', priority: 'P1' },
        { id: '2', title: 'Task B', status: 'completed', priority: 'P0' }
      ]
    });

    const tickets = await api.getTickets();

    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/api/tickets');
    expect(tickets).toHaveLength(2);
    expect(tickets[0].title).toBe('Task A');
  });

  it('executeTask performs a POST and returns success payload', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, task_id: 'abc-123' })
    });

    const result = await api.executeTask('abc-123');

    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/api/tasks/abc-123/execute', { method: 'POST' });
    expect(result.success).toBe(true);
  });
});

