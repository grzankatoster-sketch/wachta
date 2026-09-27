using Wachta.Api;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddNpgsqlDataSource(builder.Configuration.GetConnectionString("Wachta")
    ?? throw new InvalidOperationException("ConnectionStrings:Wachta is not set"));
builder.Services.AddOpenApi();
builder.Services.AddSignalR();
builder.Services.AddHostedService<LiveBroadcaster>();

var app = builder.Build();

app.MapOpenApi();
app.MapAircraftEndpoints();
app.MapDetectorEndpoints();
app.MapHub<LiveHub>("/hubs/live");

app.Run();

public partial class Program;
