using Microsoft.AspNetCore.SignalR;

namespace Wachta.Api;

/// <summary>Server-to-client only. Clients listen for "aircraft" and "alerts".</summary>
public sealed class LiveHub : Hub;
