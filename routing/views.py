from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from routing.models import Station
from routing.serializers import RouteQuerySerializer
from routing.services import ors_client, geocoding
from routing.services.corridor import stations_along_route
from routing.services.fuel import plan_fuel_stops, RouteInfeasible


class RouteView(APIView):
    def get(self, request):
        query = RouteQuerySerializer(data=request.query_params)
        if not query.is_valid():
            return Response(query.errors, status=status.HTTP_400_BAD_REQUEST)
        start_text = query.validated_data["start"]
        finish_text = query.validated_data["finish"]

        # 1. Resolve endpoints (local City table first; ORS fallback)
        try:
            s_lng, s_lat, s_label = geocoding.resolve(start_text)
            f_lng, f_lat, f_label = geocoding.resolve(finish_text)
        except geocoding.LocationNotFound as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # 2. One external routing call
        try:
            route = ors_client.directions((s_lng, s_lat), (f_lng, f_lat))
        except ors_client.ORSError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        # 3. Pure-Python fuel planning
        all_stations = list(
            Station.objects.values("name", "city", "state", "lat", "lng", "price")
        )
        candidates = stations_along_route(
            route["coords"], all_stations,
            max_detour_miles=settings.CORRIDOR_MAX_DETOUR_MILES,
        )
        try:
            stops, total_gallons, total_cost = plan_fuel_stops(
                candidates, route["distance_miles"],
                range_miles=settings.VEHICLE_RANGE_MILES, mpg=settings.VEHICLE_MPG,
            )
        except RouteInfeasible as exc:
            return Response({"error": str(exc)},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response({
            "start": s_label,
            "finish": f_label,
            "route": {"type": "LineString", "coordinates": route["coords"]},
            "total_distance_miles": round(route["distance_miles"], 1),
            "total_gallons": total_gallons,
            "total_fuel_cost": total_cost,
            "fuel_stops": [s.to_dict() for s in stops],
        })
