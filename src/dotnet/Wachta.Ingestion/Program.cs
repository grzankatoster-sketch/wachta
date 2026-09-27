using Wachta.Domain;
using Wachta.Ingestion;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddHttpClient();
builder.Services.AddNpgsqlDataSource(builder.Configuration.GetConnectionString("Wachta")
    ?? throw new InvalidOperationException("ConnectionStrings:Wachta is not set"));
builder.Services.AddSingleton<SourceFactory>();
builder.Services.AddSingleton<PositionDeduplicator>();
builder.Services.AddSingleton<MilitaryRegistry>();
builder.Services.AddSingleton<IPositionWriter, PositionWriter>();

var sourceOptions = builder.Configuration.GetSection("Sources").Get<List<SourceOptions>>() ?? [];
foreach (var options in sourceOptions)
{
    builder.Services.AddSingleton<IAircraftSource>(sp => sp.GetRequiredService<SourceFactory>().Create(options));
}

builder.Services.AddHostedService<IngestionWorker>();
builder.Build().Run();
