using Wachta.Domain;
using Wachta.Ingestion;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddSingleton(TimeProvider.System);

// Zrodla danych odrzucaja anonimowe zapytania: adsb.lol odpowiada 403, dopoki klient sie nie
// przedstawi. Skrypty w Pythonie robily to od poczatku, warstwa C# nie - i wyszlo to dopiero przy
// pierwszym uruchomieniu w kontenerze, bo testy jednostkowe nie wychodza do sieci.
// Nazwa i adres projektu sa tu po to, zeby operator zrodla mial kogo zablokowac albo o co zapytac.
builder.Services.AddHttpClient(string.Empty).ConfigureHttpClient(ConfigureUserAgent);
foreach (var id in (builder.Configuration.GetSection("Sources").Get<List<SourceOptions>>() ?? [])
         .Select(s => s.Id))
{
    builder.Services.AddHttpClient(id).ConfigureHttpClient(ConfigureUserAgent);
}

static void ConfigureUserAgent(HttpClient http)
{
    http.DefaultRequestHeaders.UserAgent.ParseAdd(WachtaHttp.UserAgent);
    http.Timeout = TimeSpan.FromSeconds(90);
}

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
